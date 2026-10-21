-- ══════════════════════════════════════════════════════════
-- LUXA.AI V6.5 - SUPABASE VERİTABANI TABLOSU
-- Bu kodu Supabase panelinde "SQL Editor" kısmına yapıştırıp "Run" butonuna basmanız yeterlidir.
-- ══════════════════════════════════════════════════════════

create table if not exists users (
  email text primary key,
  name text not null,
  password text,
  picture text,
  auth_type text default 'email',
  created_at double precision default extract(epoch from now()),
  settings jsonb default '{"theme":"theme-pink-purple","font":"font-jakarta","persona":"friendly","custom_instructions":"","temperature":0.7}'::jsonb,
  chats jsonb default '[]'::jsonb
);

-- Hızlı erişim için Row Level Security (RLS) politikası
alter table users enable row level security;
create policy "Allow all access for api key" on users for all using (true) with check (true);
