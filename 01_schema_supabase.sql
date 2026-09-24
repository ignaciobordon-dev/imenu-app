-- =====================================================================
--  iMenu App — Esquema v2 (períodos, IVA por restaurante, categorías)
--  Ejecutar COMPLETO en: Supabase → SQL Editor → New query → Run
--
--  ATENCIÓN: este script BORRA Y RECREA restaurantes, períodos y platos.
--  NO toca la tabla profiles, así que los usuarios y los roles (incluido
--  tu admin) se conservan.
--
--  Cambios respecto de la v1:
--   * Nueva tabla `restaurantes`: guarda el IVA y si el precio / el costo
--     lo incluyen. El análisis SIEMPRE se hace sobre valores sin IVA.
--   * Nueva tabla `periodos`: reemplaza el campo 'Antes' / 'Después'.
--     Un período es un rango de fechas que DEBE ser de semanas completas
--     (múltiplo exacto de 7 días), validado por la base de datos.
--   * `menu_data` ahora cuelga de un período, y la categoría es obligatoria.
--   * La vista entrega los valores netos y los promedios semanales; la
--     clasificación de la matriz se calcula en la app, porque depende de
--     si se agrupa por categoría o no.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0) Limpieza de la estructura anterior
-- ---------------------------------------------------------------------
drop view  if exists public.vw_menu_engineering;
drop view  if exists public.vw_menu_datos;
drop view  if exists public.vw_periodos;
drop table if exists public.menu_data   cascade;
drop table if exists public.periodos    cascade;
drop table if exists public.restaurantes cascade;


-- =====================================================================
-- 1) TABLA profiles  (se crea solo si no existe: no se pierden usuarios)
-- =====================================================================
create table if not exists public.profiles (
    id          uuid        primary key references auth.users(id) on delete cascade,
    email       text        not null,
    full_name   text,
    role        text        not null default 'student'
                            check (role in ('admin', 'student')),
    is_active   boolean     not null default true,
    created_at  timestamptz not null default now()
);

create index if not exists idx_profiles_role on public.profiles(role);


-- =====================================================================
-- 2) TABLA restaurantes
--    Acá vive la configuración fiscal. Se define una vez y se aplica a
--    todos los períodos del restaurante.
-- =====================================================================
create table public.restaurantes (
    id                 bigint generated always as identity primary key,
    user_id            uuid   not null references public.profiles(id) on delete cascade,
    nombre             text   not null,
    pais               text,
    moneda             text   not null default '$',

    -- Configuración de IVA
    iva_alicuota       numeric(5,2) not null default 0
                       check (iva_alicuota >= 0 and iva_alicuota < 100),
    precio_incluye_iva boolean not null default true,
    costo_incluye_iva  boolean not null default false,

    created_at         timestamptz not null default now(),

    constraint uq_restaurante_por_usuario unique (user_id, nombre)
);

comment on column public.restaurantes.iva_alicuota is
    'Porcentaje de IVA aplicable a gastronomía en el país del restaurante. Ej: 22 = 22%.';
comment on column public.restaurantes.precio_incluye_iva is
    'true = el precio cargado es el precio de carta, con IVA incluido (lo habitual).';
comment on column public.restaurantes.costo_incluye_iva is
    'false = el costo cargado ya viene neto de IVA (lo habitual, porque el IVA de compras es crédito fiscal).';

create index idx_restaurantes_user on public.restaurantes(user_id);


-- =====================================================================
-- 3) TABLA periodos
--    Un período es un rango de fechas de SEMANAS COMPLETAS.
--
--    Por qué semanas completas: en gastronomía el fin de semana vende
--    muy distinto que un martes. Un rango de 10 días incluiría dos
--    sábados y un solo martes, y el mix de platos quedaría sesgado.
--    Cualquier múltiplo exacto de 7 días contiene la misma cantidad de
--    cada día de la semana, arranque el día que arranque.
-- =====================================================================
create table public.periodos (
    id             bigint generated always as identity primary key,
    user_id        uuid   not null references public.profiles(id) on delete cascade,
    restaurante_id bigint not null references public.restaurantes(id) on delete cascade,
    etiqueta       text,
    fecha_desde    date   not null,
    fecha_hasta    date   not null,

    -- Días y semanas los calcula la base, no la app
    dias           integer generated always as
                   ((fecha_hasta - fecha_desde) + 1) stored,
    semanas        integer generated always as
                   (((fecha_hasta - fecha_desde) + 1) / 7) stored,

    created_at     timestamptz not null default now(),

    constraint ck_periodo_orden   check (fecha_hasta >= fecha_desde),
    constraint ck_semana_completa check (((fecha_hasta - fecha_desde) + 1) % 7 = 0),
    constraint uq_periodo unique (restaurante_id, fecha_desde, fecha_hasta)
);

comment on constraint ck_semana_completa on public.periodos is
    'El período debe abarcar semanas completas: (hasta - desde + 1) múltiplo de 7.';

create index idx_periodos_restaurante on public.periodos(restaurante_id);
create index idx_periodos_user        on public.periodos(user_id);


-- =====================================================================
-- 4) TABLA menu_data
--    cost y price se guardan TAL COMO LOS CARGÓ EL ALUMNO (con o sin
--    IVA según la config del restaurante). El neto lo calcula la vista,
--    así el dato original queda auditable.
-- =====================================================================
create table public.menu_data (
    id          bigint generated always as identity primary key,
    user_id     uuid   not null references public.profiles(id) on delete cascade,
    periodo_id  bigint not null references public.periodos(id) on delete cascade,

    item_name   text   not null,
    category    text   not null default 'Sin categoría',
    cost        numeric(12,2) not null default 0 check (cost  >= 0),
    price       numeric(12,2) not null default 0 check (price >= 0),
    units_sold  integer       not null default 0 check (units_sold >= 0),

    created_at  timestamptz not null default now(),

    constraint uq_plato_periodo unique (periodo_id, item_name)
);

create index idx_menu_periodo  on public.menu_data(periodo_id);
create index idx_menu_user     on public.menu_data(user_id);
create index idx_menu_category on public.menu_data(periodo_id, category);


-- =====================================================================
-- 5) FUNCIONES AUXILIARES DE SEGURIDAD
--
--    Son SECURITY DEFINER a propósito: consultar `profiles` dentro de una
--    política de `profiles` provoca "infinite recursion detected in
--    policy". Al correr con los permisos del dueño, saltean el RLS y
--    cortan el bucle.
-- =====================================================================
create or replace function public.is_admin()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
    select exists (
        select 1 from public.profiles p
        where p.id = auth.uid() and p.role = 'admin' and p.is_active
    );
$$;

create or replace function public.is_active_user()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
    select coalesce((select p.is_active from public.profiles p where p.id = auth.uid()), false);
$$;

revoke all on function public.is_admin()       from public;
revoke all on function public.is_active_user() from public;
grant execute on function public.is_admin()       to authenticated;
grant execute on function public.is_active_user() to authenticated;


-- =====================================================================
-- 6) TRIGGER: crear el perfil al registrarse
--    El rol se fuerza a 'student'. Nunca se lee de raw_user_meta_data,
--    porque ese dato lo manda el cliente y cualquiera podría pedir 'admin'.
-- =====================================================================
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, email, full_name, role, is_active)
    values (
        new.id,
        new.email,
        nullif(new.raw_user_meta_data ->> 'full_name', ''),
        'student',
        true
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();


-- =====================================================================
-- 7) TRIGGER: blindar role / is_active
--    RLS filtra FILAS, no COLUMNAS, así que las columnas sensibles se
--    protegen con un trigger.
--
--    El criterio es el ROL DE BASE DE DATOS: PostgREST (o sea, la app)
--    ejecuta como 'authenticated' o 'anon' —ahí hay que proteger—;
--    el SQL Editor lo hace como 'postgres' y un backend de confianza
--    como 'service_role', donde el docente debe poder promover admins.
-- =====================================================================
create or replace function public.protect_profile_fields()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if current_user in ('authenticated', 'anon')
       and not public.is_admin()
    then
        new.role      := old.role;
        new.is_active := old.is_active;
        new.id        := old.id;
    end if;
    return new;
end;
$$;

drop trigger if exists trg_protect_profile_fields on public.profiles;
create trigger trg_protect_profile_fields
    before update on public.profiles
    for each row execute function public.protect_profile_fields();


-- =====================================================================
-- 8) ROW LEVEL SECURITY
--    Sin política, nadie ve nada. Todo se habilita explícitamente.
-- =====================================================================

-- ---------- profiles ----------
alter table public.profiles enable row level security;

drop policy if exists profiles_select on public.profiles;
create policy profiles_select on public.profiles for select to authenticated
    using ( id = auth.uid() or public.is_admin() );

drop policy if exists profiles_insert_own on public.profiles;
create policy profiles_insert_own on public.profiles for insert to authenticated
    with check ( id = auth.uid() );

drop policy if exists profiles_update on public.profiles;
create policy profiles_update on public.profiles for update to authenticated
    using      ( id = auth.uid() or public.is_admin() )
    with check ( id = auth.uid() or public.is_admin() );

-- ---------- restaurantes ----------
alter table public.restaurantes enable row level security;

create policy restaurantes_select on public.restaurantes for select to authenticated
    using ( public.is_active_user() and ( user_id = auth.uid() or public.is_admin() ) );

create policy restaurantes_insert on public.restaurantes for insert to authenticated
    with check ( public.is_active_user() and user_id = auth.uid() );

create policy restaurantes_update on public.restaurantes for update to authenticated
    using      ( public.is_active_user() and user_id = auth.uid() )
    with check ( public.is_active_user() and user_id = auth.uid() );

create policy restaurantes_delete on public.restaurantes for delete to authenticated
    using ( public.is_active_user() and user_id = auth.uid() );

-- ---------- periodos ----------
alter table public.periodos enable row level security;

create policy periodos_select on public.periodos for select to authenticated
    using ( public.is_active_user() and ( user_id = auth.uid() or public.is_admin() ) );

create policy periodos_insert on public.periodos for insert to authenticated
    with check ( public.is_active_user() and user_id = auth.uid() );

create policy periodos_update on public.periodos for update to authenticated
    using      ( public.is_active_user() and user_id = auth.uid() )
    with check ( public.is_active_user() and user_id = auth.uid() );

create policy periodos_delete on public.periodos for delete to authenticated
    using ( public.is_active_user() and user_id = auth.uid() );

-- ---------- menu_data ----------
alter table public.menu_data enable row level security;

create policy menu_select on public.menu_data for select to authenticated
    using ( public.is_active_user() and ( user_id = auth.uid() or public.is_admin() ) );

create policy menu_insert on public.menu_data for insert to authenticated
    with check ( public.is_active_user() and user_id = auth.uid() );

create policy menu_update on public.menu_data for update to authenticated
    using      ( public.is_active_user() and user_id = auth.uid() )
    with check ( public.is_active_user() and user_id = auth.uid() );

create policy menu_delete on public.menu_data for delete to authenticated
    using ( public.is_active_user() and user_id = auth.uid() );

-- El admin queda de SOLO LECTURA sobre los datos de los alumnos.


-- =====================================================================
-- 9) VISTA vw_menu_datos
--    Entrega cada plato ya neteado de IVA y con sus promedios semanales.
--    NO calcula la matriz: eso lo hace la app, porque la clasificación
--    depende de si se agrupa por categoría o se mira el menú completo.
--
--    security_invoker = on hace que la vista respete el RLS de quien la
--    consulta. Sin esto, un alumno vería los datos de los demás.
-- =====================================================================
create or replace view public.vw_menu_datos
with (security_invoker = on) as
with neto as (
    select
        m.id,
        m.user_id,
        m.periodo_id,
        p.restaurante_id,
        r.nombre             as restaurante,
        r.moneda,
        r.iva_alicuota,
        r.precio_incluye_iva,
        r.costo_incluye_iva,
        p.etiqueta,
        p.fecha_desde,
        p.fecha_hasta,
        p.dias,
        p.semanas,
        m.item_name,
        m.category,
        m.cost               as costo_cargado,
        m.price              as precio_cargado,
        m.units_sold,
        round(
            case when r.costo_incluye_iva
                 then m.cost  / (1 + r.iva_alicuota / 100)
                 else m.cost  end, 4)                     as cost_neto,
        round(
            case when r.precio_incluye_iva
                 then m.price / (1 + r.iva_alicuota / 100)
                 else m.price end, 4)                     as price_neto
    from public.menu_data m
    join public.periodos     p on p.id = m.periodo_id
    join public.restaurantes r on r.id = p.restaurante_id
)
select
    n.*,
    (n.price_neto - n.cost_neto)                              as margen_unitario,
    (n.price_neto - n.cost_neto) * n.units_sold               as margen_total,
    n.price_neto * n.units_sold                               as ingreso_total,
    round(n.units_sold::numeric / nullif(n.semanas, 0), 2)    as unidades_semanales,
    round(((n.price_neto - n.cost_neto) * n.units_sold)
          / nullif(n.semanas, 0), 2)                          as margen_semanal,
    round((n.price_neto * n.units_sold)
          / nullif(n.semanas, 0), 2)                          as ingreso_semanal,
    case when n.price_neto > 0
         then round((n.price_neto - n.cost_neto) / n.price_neto * 100, 1)
         else 0 end                                           as margen_pct
from neto n;

grant select on public.vw_menu_datos to authenticated;


-- =====================================================================
-- 10) VISTA vw_periodos — para los selectores y el panel docente
-- =====================================================================
create or replace view public.vw_periodos
with (security_invoker = on) as
select
    p.id,
    p.user_id,
    p.restaurante_id,
    r.nombre   as restaurante,
    r.moneda,
    r.iva_alicuota,
    r.precio_incluye_iva,
    r.costo_incluye_iva,
    p.etiqueta,
    p.fecha_desde,
    p.fecha_hasta,
    p.dias,
    p.semanas,
    (select count(*) from public.menu_data m where m.periodo_id = p.id) as items,
    p.created_at
from public.periodos p
join public.restaurantes r on r.id = p.restaurante_id;

grant select on public.vw_periodos to authenticated;


-- =====================================================================
-- 11) Recordatorio: para convertir a alguien en admin
-- =====================================================================
-- update public.profiles set role = 'admin' where email = 'tu-mail@ejemplo.com';

-- =====================================================================
-- FIN. Esperado: "Success. No rows returned".
-- =====================================================================
