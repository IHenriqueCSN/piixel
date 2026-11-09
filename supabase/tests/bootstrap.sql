-- SOMENTE PostgreSQL descartável para testes. Nunca execute num projeto Supabase.
-- Reproduz o contexto JWT/RPC relevante; não é um servidor de autenticação.
create role anon;
create role authenticated;
create schema auth;
create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as $$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
grant usage on schema auth to authenticated;
grant execute on function auth.uid() to authenticated;
insert into auth.users values
    ('10000000-0000-0000-0000-000000000001'),
    ('20000000-0000-0000-0000-000000000002'),
    ('30000000-0000-0000-0000-000000000003');
