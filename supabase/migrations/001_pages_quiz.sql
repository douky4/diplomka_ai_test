-- Additive migration: existing respondents, answers and assignments are retained.
-- Applied by scripts/deploy_supabase.py; __CRYPTO_SCHEMA__ is resolved from pg_extension.
create schema if not exists quiz_private;
revoke all on schema quiz_private from public, anon, authenticated;
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

create table if not exists public.participants (
  id text primary key, age integer not null check (age > 0),
  gender text not null, experience text not null, created_at text not null
);
create table if not exists public.answers (
  id text primary key,
  participant_id text not null references public.participants(id) on delete cascade,
  question_index integer not null,
  answer text not null check (answer in ('ai', 'photo')),
  confidence integer not null check (confidence between 1 and 5),
  ai_reason text, created_at text not null,
  unique(participant_id, question_index)
);
alter table public.answers add column if not exists image_id text;
alter table public.answers add column if not exists correct_answer text;
alter table public.answers add column if not exists technique text;
alter table public.answers add column if not exists difficulty text;
alter table public.answers add column if not exists source_dataset text;
alter table public.answers add column if not exists subject_id text;
alter table public.answers add column if not exists metadata_snapshot text;
create table if not exists public.quiz_assignments (
  participant_id text not null references public.participants(id) on delete cascade,
  question_index integer not null, image_id text not null, subject_id text not null,
  public_id text not null unique, snapshot text not null,
  primary key(participant_id, question_index), unique(participant_id, subject_id)
);
create table if not exists public.allocation_state (dataset_key text primary key, pending text not null);
create index if not exists idx_answers_participant on public.answers(participant_id);
create index if not exists idx_answers_image on public.answers(image_id);

create table if not exists quiz_private.catalog (
  image_id text primary key, subject_id text not null,
  label text not null check(label in ('ai','photo')), active boolean not null,
  asset_path text not null, snapshot jsonb not null
);
create table if not exists quiz_private.settings (
  singleton boolean primary key default true check(singleton),
  dataset_key text not null, admin_hash text not null
);
create table if not exists quiz_private.admin_sessions (
  token_hash text primary key, expires_at timestamptz not null
);

-- Respondents can only call the narrowly scoped RPC functions below.
alter table public.participants enable row level security;
alter table public.answers enable row level security;
alter table public.quiz_assignments enable row level security;
alter table public.allocation_state enable row level security;
revoke all on public.participants, public.answers, public.quiz_assignments, public.allocation_state from public, anon, authenticated;
revoke all on all tables in schema quiz_private from public, anon, authenticated;

create or replace function public.quiz_status()
returns jsonb language sql security definer set search_path = '' as $$
  select jsonb_build_object('version','pages-quiz-v1',
    'ready',exists(select 1 from quiz_private.settings),
    'image_count',(select count(*) from quiz_private.catalog where active),
    'question_count',(select count(distinct subject_id) from quiz_private.catalog where active));
$$;

create or replace function public.quiz_create(p_request_id uuid, p_age integer, p_gender text, p_experience text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_id text := p_request_id::text;
  v_key text;
  v_choices jsonb;
  v_next jsonb := '{}'::jsonb;
  v_count integer;
  v_ai_count integer;
  v_index integer := 0;
  v_row record;
begin
  if p_request_id is null or p_age is null or p_age < 1 or p_age > 120
     or p_gender is null or p_gender not in ('muž','žena','jiné')
     or p_experience is null or p_experience not in ('nikdy','vyjimecne','caste','denni') then
    raise exception 'Neplatné údaje respondenta' using errcode='22023';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(73190521);
  if exists(select 1 from public.participants where id=v_id) then
    if not exists(select 1 from public.quiz_assignments where participant_id=v_id) then
      raise exception 'Identifikátor nelze použít pro nový test' using errcode='22023';
    end if;
    return jsonb_build_object('participant_id',v_id);
  end if;
  select dataset_key into strict v_key from quiz_private.settings;
  select count(distinct subject_id) into v_count from quiz_private.catalog where active;
  if v_count = 0 or exists(
    select subject_id from quiz_private.catalog where active group by subject_id
    having count(*) <> 2 or count(distinct label) <> 2
  ) then raise exception 'Dataset není připraven'; end if;
  select pending::jsonb into v_choices from public.allocation_state where dataset_key=v_key;
  if v_choices is null or v_choices='{}'::jsonb then
    v_choices := '{}'::jsonb;
    v_ai_count := v_count / 2 + case when v_count % 2=1 and random() < 0.5 then 1 else 0 end;
    for v_row in select distinct subject_id from quiz_private.catalog where active loop
      v_choices := v_choices || jsonb_build_object(v_row.subject_id, 'photo');
    end loop;
    for v_row in select subject_id from (select distinct subject_id from quiz_private.catalog where active) s
                 order by random() limit v_ai_count loop
      v_choices := v_choices || jsonb_build_object(v_row.subject_id,'ai');
    end loop;
    select jsonb_object_agg(key, case when value='ai' then 'photo' else 'ai' end)
      into v_next from jsonb_each_text(v_choices);
  end if;
  insert into public.participants(id,age,gender,experience,created_at)
    values(v_id,p_age,p_gender,p_experience,clock_timestamp()::text);
  insert into public.allocation_state(dataset_key,pending) values(v_key,v_next::text)
    on conflict(dataset_key) do update set pending=excluded.pending;
  for v_row in select c.* from quiz_private.catalog c
    where c.active and c.label=v_choices->>c.subject_id order by random() loop
    insert into public.quiz_assignments(participant_id,question_index,image_id,subject_id,public_id,snapshot)
      values(v_id,v_index,v_row.image_id,v_row.subject_id,gen_random_uuid()::text,v_row.snapshot::text);
    v_index := v_index + 1;
  end loop;
  if v_index <> v_count then raise exception 'Přidělení otázek není úplné'; end if;
  return jsonb_build_object('participant_id',v_id);
end;
$$;

create or replace function public.quiz_resume(p_participant_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_images jsonb; v_next integer;
begin
  select jsonb_agg(jsonb_build_object('image_id',q.public_id,'src',c.asset_path,'type','photo') order by q.question_index)
    into v_images from public.quiz_assignments q join quiz_private.catalog c using(image_id)
    where q.participant_id=p_participant_id::text;
  if v_images is null then raise exception 'Test nebyl nalezen' using errcode='P0002'; end if;
  select min(q.question_index) into v_next from public.quiz_assignments q
    where q.participant_id=p_participant_id::text and not exists(
      select 1 from public.answers a where a.participant_id=q.participant_id and a.question_index=q.question_index);
  return jsonb_build_object('images',v_images,'next_index',coalesce(v_next,jsonb_array_length(v_images)));
end;
$$;

create or replace function public.quiz_answer(p_participant_id uuid,p_question_index integer,p_image_id uuid,
  p_answer text,p_confidence integer,p_ai_reason text default '')
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_question jsonb;
begin
  if p_answer is null or p_answer not in ('ai','photo') or p_confidence is null or p_confidence not between 1 and 5
    or length(coalesce(p_ai_reason,'')) > 10000 then
    raise exception 'Neplatná odpověď nebo jistota' using errcode='22023';
  end if;
  select snapshot::jsonb into v_question from public.quiz_assignments
    where participant_id=p_participant_id::text and question_index=p_question_index and public_id=p_image_id::text;
  if v_question is null then raise exception 'Obrázek neodpovídá přidělené otázce' using errcode='22023'; end if;
  insert into public.answers(id,participant_id,question_index,image_id,answer,correct_answer,confidence,ai_reason,
    technique,difficulty,source_dataset,subject_id,created_at,metadata_snapshot)
  values(gen_random_uuid()::text,p_participant_id::text,p_question_index,v_question->>'image_id',p_answer,
    v_question->>'correct',p_confidence,nullif(p_ai_reason,''),v_question->>'technique',v_question->>'difficulty',
    v_question->>'source_dataset',v_question->>'subject_id',clock_timestamp()::text,v_question::text)
  on conflict(participant_id,question_index) do update set
    answer=excluded.answer,confidence=excluded.confidence,ai_reason=excluded.ai_reason,created_at=excluded.created_at;
  return jsonb_build_object('success',true);
end;
$$;

create or replace function public.quiz_admin_login(p_password text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_hash text; v_token text;
begin
  if p_password is null or length(p_password)>200 then
    return jsonb_build_object('error','Nesprávné heslo');
  end if;
  select admin_hash into v_hash from quiz_private.settings;
  if v_hash is null or __CRYPTO_SCHEMA__.crypt(p_password,v_hash) <> v_hash then
    return jsonb_build_object('error','Nesprávné heslo');
  end if;
  delete from quiz_private.admin_sessions where expires_at < now();
  v_token := encode(__CRYPTO_SCHEMA__.gen_random_bytes(32),'hex');
  insert into quiz_private.admin_sessions values(encode(__CRYPTO_SCHEMA__.digest(v_token,'sha256'),'hex'),now()+interval '4 hours');
  return jsonb_build_object('token',v_token);
end;
$$;

create or replace function quiz_private.require_admin(p_token text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if p_token is null or not exists(select 1 from quiz_private.admin_sessions
    where token_hash=encode(__CRYPTO_SCHEMA__.digest(p_token,'sha256'),'hex') and expires_at>now()) then
    raise exception 'Přihlaste se do administrace' using errcode='42501';
  end if;
end;
$$;

create or replace function public.quiz_admin_logout(p_token text)
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
  delete from quiz_private.admin_sessions where token_hash=encode(__CRYPTO_SCHEMA__.digest(p_token,'sha256'),'hex');
  return jsonb_build_object('success',true);
end;
$$;

create or replace function public.quiz_admin_data(p_token text,p_offset integer default 0)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_participants jsonb; v_answers jsonb; v_catalog jsonb;
begin
  perform quiz_private.require_admin(p_token);
  if p_offset<0 then raise exception 'Neplatná stránka'; end if;
  select coalesce(jsonb_agg(to_jsonb(p)),'[]'::jsonb) into v_participants
    from (select * from public.participants order by id offset p_offset limit 200) p;
  select coalesce(jsonb_agg(to_jsonb(a)),'[]'::jsonb) into v_answers from public.answers a
    where a.participant_id in (select v->>'id' from jsonb_array_elements(v_participants) v);
  select coalesce(jsonb_agg(jsonb_build_object('image_id',c.image_id,'src',c.asset_path,'question',c.snapshot,
    'assigned_count',(select count(*) from public.quiz_assignments q where q.image_id=c.image_id))),'[]'::jsonb)
    into v_catalog from quiz_private.catalog c;
  return jsonb_build_object('participants',v_participants,'answers',v_answers,'images',v_catalog,
    'has_more',(select count(*) from public.participants)>p_offset+200);
end;
$$;

revoke all on function quiz_private.require_admin(text) from public,anon,authenticated;
revoke all on function public.quiz_status(),public.quiz_create(uuid,integer,text,text),public.quiz_resume(uuid),
  public.quiz_answer(uuid,integer,uuid,text,integer,text),public.quiz_admin_login(text),
  public.quiz_admin_logout(text),public.quiz_admin_data(text,integer) from public,anon,authenticated;
grant execute on function public.quiz_status(),public.quiz_create(uuid,integer,text,text),public.quiz_resume(uuid),
  public.quiz_answer(uuid,integer,uuid,text,integer,text),public.quiz_admin_login(text),
  public.quiz_admin_logout(text),public.quiz_admin_data(text,integer) to anon,authenticated;
notify pgrst, 'reload schema';
