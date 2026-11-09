-- Teste de integração, apenas em banco descartável com a migração instalada.
-- Fixture: auth.users contém os UUIDs 100...001, 200...002 e 300...003;
-- auth.uid() lê request.jwt.claim.sub, como no Supabase/PostgREST.
-- Execute com psql -v ON_ERROR_STOP=1. Nenhum teste altera dados permanentemente.
begin;

do $test$
begin
    assert not has_function_privilege('anon', 'public.pii_register(text)', 'execute'),
        'anon não pode registrar';
    assert not has_schema_privilege('authenticated', 'piixelfone_private', 'usage'),
        'schema privado não pode ser acessado diretamente';
    assert not exists (select 1 from pg_tables where schemaname = 'piixelfone_private'
        and not rowsecurity), 'todas as tabelas exigem RLS';
    assert not exists (select 1 from pg_policies where schemaname = 'piixelfone_private'),
        'nenhuma política permissiva direta é necessária';
end;
$test$;

set local role authenticated;
select set_config('request.jwt.claim.sub', '10000000-0000-0000-0000-000000000001', true);
do $test$
declare p jsonb; again jsonb;
begin
    p := public.pii_register('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAE=');
    perform set_config('pii_test.number_a', p->>'number', true);
    assert (p->>'number') ~ '^[1-9][0-9]{5}$';
    again := public.pii_register('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAE=');
    assert p = again, 'registro idempotente deve preservar número e chave';
    begin
        perform public.pii_register('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAI=');
        raise exception 'ERRO: registro trocou a chave';
    exception when others then
        if sqlerrm not like 'PII_KEY_MISMATCH:%' then raise; end if;
    end;
    begin
        perform 1 from piixelfone_private.messages;
        raise exception 'ERRO: leitura direta permitida';
    exception when insufficient_privilege then null;
    end;
end;
$test$;

select set_config('request.jwt.claim.sub', '20000000-0000-0000-0000-000000000002', true);
do $test$
declare p jsonb;
begin
    p := public.pii_register('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAI=');
    perform set_config('pii_test.number_b', p->>'number', true);
end;
$test$;
select set_config('request.jwt.claim.sub', '30000000-0000-0000-0000-000000000003', true);
select public.pii_register('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM=');

select set_config('request.jwt.claim.sub', '10000000-0000-0000-0000-000000000001', true);
do $test$
begin
    assert public.pii_lookup(current_setting('pii_test.number_b'))->>'user_id'
        = '20000000-0000-0000-0000-000000000002';
    begin
        perform public.pii_send('aaaaaaaa-0000-0000-0000-000000000001',
            '20000000-0000-0000-0000-000000000002', encode(repeat('a', 40)::bytea, 'base64'));
        raise exception 'ERRO: envio sem contato aceito';
    exception when others then
        if sqlerrm not like 'PII_CONTACT_REQUIRED:%' then raise; end if;
    end;
    perform public.pii_request('20000000-0000-0000-0000-000000000002');
    perform public.pii_request('20000000-0000-0000-0000-000000000002');
    assert jsonb_array_length(public.pii_contacts()) = 1;
    assert public.pii_contacts()->0->>'state' = 'pending';
    assert public.pii_contacts()->0->>'incoming' = 'false';
    begin
        perform public.pii_accept('20000000-0000-0000-0000-000000000002');
        raise exception 'ERRO: remetente aceitou a própria solicitação';
    exception when others then
        if sqlerrm not like 'PII_CONTACT_FORBIDDEN:%' then raise; end if;
    end;
end;
$test$;

select set_config('request.jwt.claim.sub', '20000000-0000-0000-0000-000000000002', true);
do $test$
begin
    assert public.pii_contacts()->0->>'incoming' = 'true';
    perform public.pii_accept('10000000-0000-0000-0000-000000000001');
    perform public.pii_accept('10000000-0000-0000-0000-000000000001');
    assert public.pii_contacts()->0->>'state' = 'accepted';
end;
$test$;

select set_config('request.jwt.claim.sub', '10000000-0000-0000-0000-000000000001', true);
do $test$
begin
    perform public.pii_send('aaaaaaaa-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000002', encode(repeat('a', 40)::bytea, 'base64'));
    perform public.pii_send('aaaaaaaa-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000002', encode(repeat('a', 40)::bytea, 'base64'));
    assert jsonb_array_length(public.pii_inbox()) = 0, 'remetente não recebe a própria mensagem';
    begin
        perform public.pii_send('aaaaaaaa-0000-0000-0000-000000000001',
            '20000000-0000-0000-0000-000000000002', encode(repeat('b', 40)::bytea, 'base64'));
        raise exception 'ERRO: mesmo UUID sobrescreveu conteúdo';
    exception when others then
        if sqlerrm not like 'PII_MESSAGE_CONFLICT:%' then raise; end if;
    end;
    begin
        perform public.pii_ack('aaaaaaaa-0000-0000-0000-000000000001');
        raise exception 'ERRO: remetente confirmou a entrega';
    exception when others then
        if sqlerrm not like 'PII_MESSAGE_NOT_FOUND:%' then raise; end if;
    end;
end;
$test$;

select set_config('request.jwt.claim.sub', '30000000-0000-0000-0000-000000000003', true);
do $test$
begin
    assert public.pii_inbox() = '[]'::jsonb;
    assert public.pii_contacts() = '[]'::jsonb;
    assert public.pii_statuses(array['aaaaaaaa-0000-0000-0000-000000000001'::uuid]) = '[]'::jsonb;
    begin
        perform public.pii_ack('aaaaaaaa-0000-0000-0000-000000000001');
        raise exception 'ERRO: terceiro confirmou a entrega';
    exception when others then
        if sqlerrm not like 'PII_MESSAGE_NOT_FOUND:%' then raise; end if;
    end;
end;
$test$;

select set_config('request.jwt.claim.sub', '20000000-0000-0000-0000-000000000002', true);
do $test$
declare inbox jsonb;
begin
    inbox := public.pii_inbox();
    assert jsonb_array_length(inbox) = 1, 'reenvio não pode duplicar';
    assert inbox->0->>'sender' = '10000000-0000-0000-0000-000000000001';
    assert inbox->0->>'payload' = encode(repeat('a', 40)::bytea, 'base64');
    perform public.pii_ack('aaaaaaaa-0000-0000-0000-000000000001');
    perform public.pii_ack('aaaaaaaa-0000-0000-0000-000000000001');
    assert public.pii_inbox() = '[]'::jsonb;
end;
$test$;

select set_config('request.jwt.claim.sub', '10000000-0000-0000-0000-000000000001', true);
do $test$
declare state jsonb; p jsonb;
begin
    state := public.pii_statuses(array['aaaaaaaa-0000-0000-0000-000000000001'::uuid]);
    assert state->0->>'delivered_at' is not null;
    assert state->0->>'rejected_at' is null;
    -- Repetição tardia, depois do ACK, também é idempotente.
    perform public.pii_send('aaaaaaaa-0000-0000-0000-000000000001',
        '20000000-0000-0000-0000-000000000002', encode(repeat('a', 40)::bytea, 'base64'));
    perform public.pii_send('aaaaaaaa-0000-0000-0000-000000000002',
        '20000000-0000-0000-0000-000000000002', encode(repeat('b', 40)::bytea, 'base64'));
    p := public.pii_regenerate();
    assert p->>'number' <> current_setting('pii_test.number_a');
    assert p->>'user_id' = '10000000-0000-0000-0000-000000000001';
    assert p->>'public_key' = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAE=';
    perform set_config('pii_test.new_number_a', p->>'number', true);
    assert public.pii_lookup(current_setting('pii_test.number_a')) is null;
    perform public.pii_regenerate();
    perform public.pii_regenerate();
    begin
        perform public.pii_regenerate();
        raise exception 'ERRO: limite de regeneração ignorado';
    exception when others then
        if sqlerrm not like 'PII_RATE_LIMIT:%' then raise; end if;
    end;
end;
$test$;

select set_config('request.jwt.claim.sub', '20000000-0000-0000-0000-000000000002', true);
do $test$
begin
    assert jsonb_array_length(public.pii_inbox()) = 1, 'regeneração preserva fila';
    assert public.pii_contacts()->0->>'state' = 'accepted', 'regeneração preserva contatos';
    perform public.pii_reject('aaaaaaaa-0000-0000-0000-000000000002');
    perform public.pii_reject('aaaaaaaa-0000-0000-0000-000000000002');
    assert public.pii_inbox() = '[]'::jsonb, 'envelope inválido sai da fila';
    begin
        perform public.pii_ack('aaaaaaaa-0000-0000-0000-000000000002');
        raise exception 'ERRO: envelope recusado marcado como entregue';
    exception when others then
        if sqlerrm not like 'PII_MESSAGE_REJECTED:%' then raise; end if;
    end;
end;
$test$;

select set_config('request.jwt.claim.sub', '10000000-0000-0000-0000-000000000001', true);
do $test$
declare state jsonb;
begin
    state := public.pii_statuses(array['aaaaaaaa-0000-0000-0000-000000000002'::uuid]);
    assert state->0->>'delivered_at' is null;
    assert state->0->>'rejected_at' is not null;
end;
$test$;

reset role;
do $test$
begin
    assert exists (select 1 from piixelfone_private.numbers
        where number = current_setting('pii_test.number_a') and retired_at is not null),
        'número antigo permanece reservado';
    assert not exists (select 1 from piixelfone_private.messages where payload is not null),
        'ACK e rejeição removem o envelope do servidor';
end;
$test$;
rollback;
\echo 'Piixelfone: testes de integração SQL passaram.'
