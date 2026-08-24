-- BKTSTR v0.3.5 GitHub-through-Supabase recovery bridge.
-- Stores public repository blobs as base64 so source can be recovered exactly
-- when an agent cannot reach GitHub directly. No credentials are stored here.

create table if not exists public.bktstr_repo_snapshots (
    snapshot_id uuid primary key default gen_random_uuid(),
    repo_owner text not null,
    repo_name text not null,
    requested_ref text not null,
    git_commit text,
    tree_sha text,
    commit_request_id bigint,
    tree_request_id bigint,
    status text not null default 'commit_requested',
    created_at timestamptz not null default now(),
    completed_at timestamptz
);

create table if not exists public.bktstr_repo_blob_requests (
    snapshot_id uuid not null references public.bktstr_repo_snapshots(snapshot_id) on delete cascade,
    path text not null,
    blob_sha text not null,
    request_id bigint not null unique,
    created_at timestamptz not null default now(),
    primary key (snapshot_id, path)
);

create table if not exists public.bktstr_repo_files (
    snapshot_id uuid not null references public.bktstr_repo_snapshots(snapshot_id) on delete cascade,
    path text not null,
    blob_sha text not null,
    encoding text not null,
    content_base64 text not null,
    byte_size bigint,
    collected_at timestamptz not null default now(),
    primary key (snapshot_id, path)
);

alter table public.bktstr_repo_snapshots enable row level security;
alter table public.bktstr_repo_blob_requests enable row level security;
alter table public.bktstr_repo_files enable row level security;

create or replace function public.bktstr_github_enqueue_commit(
    p_owner text,
    p_repo text,
    p_ref text default 'main'
)
returns table(snapshot_id uuid, request_id bigint)
language plpgsql
security definer
set search_path = public, net, pg_temp
as $$
declare
    v_snapshot uuid := gen_random_uuid();
    v_request bigint;
begin
    if p_owner !~ '^[A-Za-z0-9_.-]+$' or p_repo !~ '^[A-Za-z0-9_.-]+$' or p_ref !~ '^[A-Za-z0-9_.-]+$' then
        raise exception 'owner, repo, and ref must contain only safe GitHub path characters';
    end if;

    insert into public.bktstr_repo_snapshots(snapshot_id, repo_owner, repo_name, requested_ref)
    values (v_snapshot, p_owner, p_repo, p_ref);

    v_request := net.http_get(
        url := format('https://api.github.com/repos/%s/%s/commits/%s', p_owner, p_repo, p_ref),
        headers := jsonb_build_object(
            'User-Agent', 'bktstr-supabase-bridge',
            'Accept', 'application/vnd.github+json'
        ),
        timeout_milliseconds := 120000
    );

    update public.bktstr_repo_snapshots
    set commit_request_id = v_request
    where bktstr_repo_snapshots.snapshot_id = v_snapshot;

    return query select v_snapshot, v_request;
end;
$$;

create or replace function public.bktstr_github_enqueue_tree(p_snapshot uuid)
returns bigint
language plpgsql
security definer
set search_path = public, net, pg_temp
as $$
declare
    v_snapshot public.bktstr_repo_snapshots%rowtype;
    v_status integer;
    v_content text;
    v_commit text;
    v_tree text;
    v_request bigint;
begin
    select * into strict v_snapshot
    from public.bktstr_repo_snapshots
    where snapshot_id = p_snapshot;

    select status_code, content into v_status, v_content
    from net._http_response
    where id = v_snapshot.commit_request_id;

    if not found then
        raise exception 'commit response not ready for snapshot %', p_snapshot;
    end if;
    if v_status <> 200 then
        raise exception 'GitHub commit request failed with HTTP %', v_status;
    end if;

    v_commit := (v_content::jsonb ->> 'sha');
    v_tree := (v_content::jsonb #>> '{commit,tree,sha}');
    if v_commit !~ '^[0-9a-f]{40}$' or v_tree !~ '^[0-9a-f]{40}$' then
        raise exception 'GitHub commit response did not contain valid commit/tree SHAs';
    end if;

    v_request := net.http_get(
        url := format(
            'https://api.github.com/repos/%s/%s/git/trees/%s',
            v_snapshot.repo_owner,
            v_snapshot.repo_name,
            v_tree
        ),
        params := jsonb_build_object('recursive', '1'),
        headers := jsonb_build_object(
            'User-Agent', 'bktstr-supabase-bridge',
            'Accept', 'application/vnd.github+json'
        ),
        timeout_milliseconds := 120000
    );

    update public.bktstr_repo_snapshots
    set git_commit = v_commit,
        tree_sha = v_tree,
        tree_request_id = v_request,
        status = 'tree_requested'
    where snapshot_id = p_snapshot;

    return v_request;
end;
$$;

create or replace function public.bktstr_github_enqueue_blobs(p_snapshot uuid)
returns integer
language plpgsql
security definer
set search_path = public, net, pg_temp
as $$
declare
    v_snapshot public.bktstr_repo_snapshots%rowtype;
    v_status integer;
    v_content text;
    v_count integer;
begin
    select * into strict v_snapshot
    from public.bktstr_repo_snapshots
    where snapshot_id = p_snapshot;

    select status_code, content into v_status, v_content
    from net._http_response
    where id = v_snapshot.tree_request_id;

    if not found then
        raise exception 'tree response not ready for snapshot %', p_snapshot;
    end if;
    if v_status <> 200 then
        raise exception 'GitHub tree request failed with HTTP %', v_status;
    end if;

    with entries as (
        select
            item ->> 'path' as path,
            item ->> 'sha' as blob_sha
        from jsonb_array_elements(coalesce(v_content::jsonb -> 'tree', '[]'::jsonb)) as item
        where item ->> 'type' = 'blob'
          and item ->> 'sha' ~ '^[0-9a-f]{40}$'
          and item ->> 'path' ~ '^[A-Za-z0-9_./-]+$'
          and item ->> 'path' not like '%/__pycache__/%'
          and item ->> 'path' not like '__pycache__/%'
          and item ->> 'path' !~ '\.py[co]$'
          and item ->> 'path' not like '%.pytest_cache/%'
    ), missing as (
        select entries.path, entries.blob_sha
        from entries
        where not exists (
            select 1
            from public.bktstr_repo_blob_requests existing
            where existing.snapshot_id = p_snapshot
              and existing.path = entries.path
        )
    )
    insert into public.bktstr_repo_blob_requests(snapshot_id, path, blob_sha, request_id)
    select
        p_snapshot,
        missing.path,
        missing.blob_sha,
        net.http_get(
            url := format(
                'https://raw.githubusercontent.com/%s/%s/%s/%s',
                v_snapshot.repo_owner,
                v_snapshot.repo_name,
                v_snapshot.git_commit,
                missing.path
            ),
            headers := jsonb_build_object(
                'User-Agent', 'bktstr-supabase-bridge'
            ),
            timeout_milliseconds := 120000
        )
    from missing;

    get diagnostics v_count = row_count;

    update public.bktstr_repo_snapshots
    set status = 'blobs_requested'
    where snapshot_id = p_snapshot;

    return v_count;
end;
$$;

create or replace function public.bktstr_github_collect_blobs(p_snapshot uuid)
returns table(collected integer, pending integer, failed integer)
language plpgsql
security definer
set search_path = public, net, pg_temp
as $$
declare
    v_total integer;
    v_collected integer;
    v_pending integer;
    v_failed integer;
begin
    if not exists (
        select 1 from public.bktstr_repo_snapshots where snapshot_id = p_snapshot
    ) then
        raise exception 'unknown snapshot %', p_snapshot;
    end if;

    insert into public.bktstr_repo_files(
        snapshot_id,
        path,
        blob_sha,
        encoding,
        content_base64,
        byte_size,
        collected_at
    )
    select
        requests.snapshot_id,
        requests.path,
        requests.blob_sha,
        'base64',
        encode(convert_to(response.content, 'UTF8'), 'base64'),
        octet_length(convert_to(response.content, 'UTF8')),
        now()
    from public.bktstr_repo_blob_requests requests
    join net._http_response response on response.id = requests.request_id
    where requests.snapshot_id = p_snapshot
      and response.status_code = 200
      and response.content is not null
    on conflict (snapshot_id, path) do update
    set blob_sha = excluded.blob_sha,
        encoding = excluded.encoding,
        content_base64 = excluded.content_base64,
        byte_size = excluded.byte_size,
        collected_at = excluded.collected_at;

    select count(*) into v_total
    from public.bktstr_repo_blob_requests
    where snapshot_id = p_snapshot;

    select count(*) into v_collected
    from public.bktstr_repo_files
    where snapshot_id = p_snapshot;

    select count(*) into v_pending
    from public.bktstr_repo_blob_requests requests
    left join net._http_response response on response.id = requests.request_id
    where requests.snapshot_id = p_snapshot
      and response.id is null;

    v_failed := greatest(v_total - v_collected - v_pending, 0);

    if v_total > 0 and v_pending = 0 and v_failed = 0 and v_collected = v_total then
        update public.bktstr_repo_snapshots
        set status = 'complete', completed_at = now()
        where snapshot_id = p_snapshot;
    end if;

    return query select v_collected, v_pending, v_failed;
end;
$$;

revoke all on table public.bktstr_repo_snapshots from anon, authenticated;
revoke all on table public.bktstr_repo_blob_requests from anon, authenticated;
revoke all on table public.bktstr_repo_files from anon, authenticated;
revoke execute on function public.bktstr_github_enqueue_commit(text, text, text) from public, anon, authenticated;
revoke execute on function public.bktstr_github_enqueue_tree(uuid) from public, anon, authenticated;
revoke execute on function public.bktstr_github_enqueue_blobs(uuid) from public, anon, authenticated;
revoke execute on function public.bktstr_github_collect_blobs(uuid) from public, anon, authenticated;

-- Lock down the legacy emergency staging table if it exists from pre-v0.3.5 recovery work.
do $$
begin
    if to_regclass('public.bktstr_repo_fetch_staging') is not null then
        execute 'alter table public.bktstr_repo_fetch_staging enable row level security';
        execute 'revoke all on table public.bktstr_repo_fetch_staging from anon, authenticated';
    end if;
end;
$$;
