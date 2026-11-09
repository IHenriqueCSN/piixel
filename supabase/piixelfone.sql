-- Piixelfone, versão 1. Execute todo este arquivo no SQL Editor do Supabase.
-- O cliente nunca recebe service_role. O conteúdo das mensagens já chega cifrado.
begin;

create schema if not exists piixelfone_private;
revoke all on schema piixelfone_private from public, anon, authenticated;

create table if not exists piixelfone_private.numbers (
    number text primary key check (number ~ '^[1-9][0-9]{5}$'),
    user_id uuid not null references auth.users(id) on delete cascade,
    created_at timestamptz not null default now(),
    retired_at timestamptz
);
-- Não permita a reutilização nem quando uma conta for excluída.
alter table piixelfone_private.numbers drop constraint if exists numbers_user_id_fkey;

create table if not exists piixelfone_private.profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    number text not null unique references piixelfone_private.numbers(number),
    public_key text not null check (
        public_key ~ '^[A-Za-z0-9+/]{43}=$'
        and octet_length(decode(public_key, 'base64')) = 32
    ),
    created_at timestamptz not null default now()
);

create table if not exists piixelfone_private.contacts (
    low_id uuid not null references piixelfone_private.profiles(user_id) on delete cascade,
    high_id uuid not null references piixelfone_private.profiles(user_id) on delete cascade,
    requested_by uuid not null,
    state text not null check (state in ('pending', 'accepted', 'declined')),
    updated_at timestamptz not null default now(),
    primary key (low_id, high_id),
    check (low_id < high_id),
    check (requested_by in (low_id, high_id))
);

create table if not exists piixelfone_private.messages (
    id uuid primary key,
    sender uuid not null references piixelfone_private.profiles(user_id) on delete cascade,
    recipient uuid not null references piixelfone_private.profiles(user_id) on delete cascade,
    payload text,
    payload_hash bytea not null,
    created_at timestamptz not null default now(),
    delivered_at timestamptz,
    rejected_at timestamptz,
    check (sender <> recipient),
    check (payload is null or octet_length(payload) between 56 and 180000),
    check (delivered_at is null or rejected_at is null),
    check ((delivered_at is null and rejected_at is null) = (payload is not null))
);
create index if not exists pii_pending_recipient
    on piixelfone_private.messages(recipient, created_at, id)
    where delivered_at is null and rejected_at is null;
create index if not exists pii_sender on piixelfone_private.messages(sender);

create table if not exists piixelfone_private.rate_limits (
    user_id uuid not null references auth.users(id) on delete cascade,
    scope text not null,
    period bigint not null,
    hits bigint not null,
    primary key (user_id, scope)
);

alter table piixelfone_private.numbers enable row level security;
alter table piixelfone_private.profiles enable row level security;
alter table piixelfone_private.contacts enable row level security;
alter table piixelfone_private.messages enable row level security;
alter table piixelfone_private.rate_limits enable row level security;
revoke all on all tables in schema piixelfone_private from public, anon, authenticated;

-- Apenas os RPCs SECURITY DEFINER abaixo alcançam as tabelas. Não há políticas
-- permissivas: acesso direto (inclusive com JWT autenticado) é negado.
create or replace function piixelfone_private.actor()
returns uuid language plpgsql stable set search_path = '' as $$
declare v_actor uuid := auth.uid();
begin
    if v_actor is null then
        raise exception 'PII_AUTH_REQUIRED: Autenticação necessária.' using errcode = '28000';
    end if;
    return v_actor;
end;
$$;

create or replace function piixelfone_private.take_rate(
    p_actor uuid, p_scope text, p_limit bigint, p_seconds integer, p_cost bigint default 1
) returns void language plpgsql set search_path = '' as $$
declare
    v_period bigint := floor(extract(epoch from clock_timestamp()) / p_seconds)::bigint;
    v_hits bigint;
begin
    insert into piixelfone_private.rate_limits(user_id, scope, period, hits)
        values (p_actor, p_scope, v_period, p_cost)
    on conflict (user_id, scope) do update
        set period = excluded.period,
            hits = case when piixelfone_private.rate_limits.period = excluded.period
                then piixelfone_private.rate_limits.hits + p_cost else p_cost end
    returning hits into v_hits;
    if v_hits > p_limit then
        raise exception 'PII_RATE_LIMIT: Limite temporário atingido. Tente novamente mais tarde.' using errcode = 'P0429';
    end if;
end;
$$;

create or replace function piixelfone_private.reserve_number(p_actor uuid)
returns text language plpgsql set search_path = '' as $$
declare v_random bigint; v_number text; v_inserted text;
begin
    for v_attempt in 1..100 loop
        -- UUID v4 usa o gerador criptográfico do PostgreSQL. Rejeição evita viés
        -- no módulo de 900.000; estes primeiros 32 bits não incluem bits de versão.
        v_random := ('x' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 8))::bit(32)::bigint;
        if v_random >= 4294800000 then continue; end if;
        v_number := (100000 + (v_random % 900000))::text;
        insert into piixelfone_private.numbers(number, user_id)
            values (v_number, p_actor) on conflict do nothing returning number into v_inserted;
        if v_inserted is not null then return v_inserted; end if;
    end loop;
    raise exception 'PII_NUMBER_UNAVAILABLE: Não foi possível reservar um número. Tente novamente.';
end;
$$;

create or replace function piixelfone_private.require_profile(p_actor uuid)
returns void language plpgsql stable set search_path = '' as $$
begin
    if not exists (select 1 from piixelfone_private.profiles where user_id = p_actor) then
        raise exception 'PII_REGISTRATION_REQUIRED: Registre este Piixelfone primeiro.';
    end if;
end;
$$;

create or replace function public.pii_register(p_public_key text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := piixelfone_private.actor(); v_profile piixelfone_private.profiles;
begin
    if p_public_key is null or p_public_key !~ '^[A-Za-z0-9+/]{43}=$'
        or octet_length(decode(p_public_key, 'base64')) <> 32
        or encode(decode(p_public_key, 'base64'), 'base64') <> p_public_key then
        raise exception 'PII_INVALID_KEY: Chave pública inválida.';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(v_actor::text, 764345));
    select * into v_profile from piixelfone_private.profiles where user_id = v_actor;
    if found then
        if v_profile.public_key <> p_public_key then
            raise exception 'PII_KEY_MISMATCH: A identidade local não corresponde ao registro do servidor.';
        end if;
    else
        insert into piixelfone_private.profiles(user_id, number, public_key)
            values (v_actor, piixelfone_private.reserve_number(v_actor), p_public_key)
            returning * into v_profile;
    end if;
    return jsonb_build_object('user_id', v_profile.user_id, 'number', v_profile.number,
        'public_key', v_profile.public_key);
end;
$$;

create or replace function public.pii_lookup(p_number text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := piixelfone_private.actor(); v_result jsonb;
begin
    perform piixelfone_private.require_profile(v_actor);
    perform piixelfone_private.take_rate(v_actor, 'lookup_hour', 30, 3600);
    if p_number is null or p_number !~ '^[1-9][0-9]{5}$' then
        raise exception 'PII_INVALID_NUMBER: Informe os seis algarismos do Piixelfone.';
    end if;
    select jsonb_build_object('user_id', p.user_id, 'number', p.number, 'public_key', p.public_key)
        into v_result from piixelfone_private.profiles p where p.number = p_number;
    return v_result;
end;
$$;

create or replace function public.pii_regenerate()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := piixelfone_private.actor(); v_old text; v_profile piixelfone_private.profiles;
begin
    perform piixelfone_private.require_profile(v_actor);
    perform pg_advisory_xact_lock(hashtextextended(v_actor::text, 764345));
    perform piixelfone_private.take_rate(v_actor, 'regenerate_day', 3, 86400);
    select number into v_old from piixelfone_private.profiles where user_id = v_actor for update;
    update piixelfone_private.numbers set retired_at = now() where number = v_old;
    update piixelfone_private.profiles set number = piixelfone_private.reserve_number(v_actor)
        where user_id = v_actor returning * into v_profile;
    return jsonb_build_object('user_id', v_profile.user_id, 'number', v_profile.number,
        'public_key', v_profile.public_key);
end;
$$;

create or replace function public.pii_contacts()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := piixelfone_private.actor(); v_result jsonb;
begin
    perform piixelfone_private.require_profile(v_actor);
    select coalesce(jsonb_agg(jsonb_build_object(
        'user_id', p.user_id, 'number', p.number, 'public_key', p.public_key,
        'state', c.state, 'incoming', c.requested_by <> v_actor) order by c.updated_at desc), '[]'::jsonb)
        into v_result
        from piixelfone_private.contacts c
        join piixelfone_private.profiles p on p.user_id = case
            when c.low_id = v_actor then c.high_id else c.low_id end
        where v_actor in (c.low_id, c.high_id);
    return v_result;
end;
$$;

create or replace function public.pii_request(p_peer uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare
    v_actor uuid := piixelfone_private.actor();
    v_contact piixelfone_private.contacts;
    v_low uuid := least(v_actor, p_peer); v_high uuid := greatest(v_actor, p_peer);
begin
    perform piixelfone_private.require_profile(v_actor);
    if p_peer is null or p_peer = v_actor then raise exception 'PII_INVALID_PEER: Contato inválido.'; end if;
    perform piixelfone_private.require_profile(p_peer);
    perform pg_advisory_xact_lock(hashtextextended(v_low::text || v_high::text, 43432));
    select * into v_contact from piixelfone_private.contacts
        where low_id = v_low and high_id = v_high for update;
    if found and v_contact.state in ('accepted', 'pending') then return; end if;
    if found and v_contact.updated_at > now() - interval '24 hours' then
        raise exception 'PII_CONTACT_COOLDOWN: Aguarde antes de reenviar esta solicitação.';
    end if;
    perform piixelfone_private.take_rate(v_actor, 'request_hour', 10, 3600);
    if (select count(*) from piixelfone_private.contacts
            where requested_by = v_actor and state = 'pending') >= 20 then
        raise exception 'PII_PENDING_LIMIT: Há muitas solicitações pendentes.';
    end if;
    insert into piixelfone_private.contacts(low_id, high_id, requested_by, state)
        values (v_low, v_high, v_actor, 'pending')
    on conflict (low_id, high_id) do update
        set requested_by = v_actor, state = 'pending', updated_at = now();
end;
$$;

create or replace function public.pii_accept(p_peer uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := piixelfone_private.actor(); v_contact piixelfone_private.contacts;
begin
    select * into v_contact from piixelfone_private.contacts
        where low_id = least(v_actor, p_peer) and high_id = greatest(v_actor, p_peer) for update;
    if not found then raise exception 'PII_CONTACT_NOT_FOUND: Solicitação não encontrada.'; end if;
    if v_contact.state = 'accepted' then return; end if;
    if v_contact.state <> 'pending' or v_contact.requested_by = v_actor then
        raise exception 'PII_CONTACT_FORBIDDEN: Apenas o destinatário pode aceitar a solicitação.';
    end if;
    update piixelfone_private.contacts set state = 'accepted', updated_at = now()
        where low_id = v_contact.low_id and high_id = v_contact.high_id;
end;
$$;

create or replace function public.pii_decline(p_peer uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := piixelfone_private.actor(); v_contact piixelfone_private.contacts;
begin
    select * into v_contact from piixelfone_private.contacts
        where low_id = least(v_actor, p_peer) and high_id = greatest(v_actor, p_peer) for update;
    if not found then raise exception 'PII_CONTACT_NOT_FOUND: Solicitação não encontrada.'; end if;
    if v_contact.state = 'declined' then return; end if;
    if v_contact.state <> 'pending' or v_contact.requested_by = v_actor then
        raise exception 'PII_CONTACT_FORBIDDEN: Apenas o destinatário pode recusar a solicitação.';
    end if;
    update piixelfone_private.contacts set state = 'declined', updated_at = now()
        where low_id = v_contact.low_id and high_id = v_contact.high_id;
end;
$$;

create or replace function public.pii_send(p_id uuid, p_recipient uuid, p_payload text)
returns void language plpgsql security definer set search_path = '' as $$
declare
    v_actor uuid := piixelfone_private.actor();
    v_existing piixelfone_private.messages;
    v_hash bytea;
begin
    perform piixelfone_private.require_profile(v_actor);
    if p_id is null or p_recipient is null or p_recipient = v_actor then
        raise exception 'PII_INVALID_MESSAGE: Mensagem inválida.';
    end if;
    if p_payload is null or octet_length(p_payload) not between 56 and 180000
        or p_payload !~ '^[A-Za-z0-9+/]*={0,2}$' or length(p_payload) % 4 <> 0 then
        raise exception 'PII_INVALID_PAYLOAD: Envelope cifrado inválido ou muito grande.';
    end if;
    if octet_length(decode(p_payload, 'base64')) < 40 then
        raise exception 'PII_INVALID_PAYLOAD: Envelope cifrado inválido.';
    end if;
    v_hash := sha256(convert_to(p_payload, 'UTF8'));
    -- Uma repetição após timeout/ACK não duplica a mensagem nem ressuscita o conteúdo.
    perform pg_advisory_xact_lock(hashtextextended(p_id::text, 893477));
    select * into v_existing from piixelfone_private.messages where id = p_id;
    if found then
        if v_existing.sender = v_actor and v_existing.recipient = p_recipient
            and v_existing.payload_hash = v_hash then return; end if;
        raise exception 'PII_MESSAGE_CONFLICT: Identificador de mensagem já utilizado.';
    end if;
    if not exists (select 1 from piixelfone_private.contacts
            where low_id = least(v_actor, p_recipient) and high_id = greatest(v_actor, p_recipient)
            and state = 'accepted') then
        raise exception 'PII_CONTACT_REQUIRED: O contato precisa aceitar a conversa antes do envio.';
    end if;
    perform piixelfone_private.take_rate(v_actor, 'send_minute', 60, 60);
    perform piixelfone_private.take_rate(v_actor, 'send_day', 1000, 86400);
    perform piixelfone_private.take_rate(v_actor, 'bytes_day', 10485760, 86400, octet_length(p_payload));
    if (select count(*) from piixelfone_private.messages where recipient = p_recipient
            and delivered_at is null and rejected_at is null) >= 5000 then
        raise exception 'PII_MAILBOX_FULL: A fila do destinatário está cheia. Tente novamente mais tarde.';
    end if;
    insert into piixelfone_private.messages(id, sender, recipient, payload, payload_hash)
        values (p_id, v_actor, p_recipient, p_payload, v_hash);
end;
$$;

create or replace function public.pii_inbox()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := piixelfone_private.actor(); v_result jsonb;
begin
    perform piixelfone_private.require_profile(v_actor);
    select coalesce(jsonb_agg(to_jsonb(m) order by m.created_at, m.id), '[]'::jsonb)
        into v_result from (
            select id, sender, recipient, payload, created_at, delivered_at, rejected_at
            from piixelfone_private.messages where recipient = v_actor
                and delivered_at is null and rejected_at is null
            order by created_at, id limit 10
        ) m;
    return v_result;
end;
$$;

create or replace function public.pii_ack(p_id uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := piixelfone_private.actor(); v_message piixelfone_private.messages;
begin
    select * into v_message from piixelfone_private.messages
        where id = p_id and recipient = v_actor for update;
    if not found then raise exception 'PII_MESSAGE_NOT_FOUND: Mensagem não encontrada.'; end if;
    if v_message.rejected_at is not null then raise exception 'PII_MESSAGE_REJECTED: Mensagem recusada.'; end if;
    if v_message.delivered_at is not null then return; end if;
    update piixelfone_private.messages set delivered_at = now(), payload = null where id = p_id;
end;
$$;

create or replace function public.pii_reject(p_id uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := piixelfone_private.actor(); v_message piixelfone_private.messages;
begin
    select * into v_message from piixelfone_private.messages
        where id = p_id and recipient = v_actor for update;
    if not found then raise exception 'PII_MESSAGE_NOT_FOUND: Mensagem não encontrada.'; end if;
    if v_message.delivered_at is not null or v_message.rejected_at is not null then return; end if;
    update piixelfone_private.messages set rejected_at = now(), payload = null where id = p_id;
end;
$$;

create or replace function public.pii_statuses(p_ids uuid[])
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := piixelfone_private.actor(); v_result jsonb;
begin
    if p_ids is null or coalesce(cardinality(p_ids), 0) > 100 then
        raise exception 'PII_INVALID_BATCH: Consulte até 100 mensagens por vez.';
    end if;
    select coalesce(jsonb_agg(jsonb_build_object('id', m.id,
        'delivered_at', m.delivered_at, 'rejected_at', m.rejected_at)), '[]'::jsonb)
        into v_result from piixelfone_private.messages m
        where m.sender = v_actor and m.id = any(p_ids);
    return v_result;
end;
$$;

revoke execute on all functions in schema piixelfone_private from public, anon, authenticated;
revoke execute on function public.pii_register(text), public.pii_lookup(text),
    public.pii_regenerate(), public.pii_contacts(), public.pii_request(uuid),
    public.pii_accept(uuid), public.pii_decline(uuid), public.pii_send(uuid, uuid, text),
    public.pii_inbox(), public.pii_ack(uuid), public.pii_reject(uuid), public.pii_statuses(uuid[])
    from public, anon, authenticated;
grant execute on function public.pii_register(text), public.pii_lookup(text),
    public.pii_regenerate(), public.pii_contacts(), public.pii_request(uuid),
    public.pii_accept(uuid), public.pii_decline(uuid), public.pii_send(uuid, uuid, text),
    public.pii_inbox(), public.pii_ack(uuid), public.pii_reject(uuid), public.pii_statuses(uuid[])
    to authenticated;

comment on schema piixelfone_private is
    'Piixelfone v1: fila E2EE privada, sem acesso direto por clientes.';
notify pgrst, 'reload schema';
commit;
