# Supabase deployment

Project: Salvation Mahumane VPN (`wfqsmsmozqvwuejpftfh`) in the confirmed free organization. Region: Frankfurt.

The backend uses an application-only `salvation_backend` login, granted DML on the 17 named VPN tables and usage on its audit/usage sequences. It has no superuser, create-role, create-database or table-ownership privileges. All application tables have RLS enabled, policies target only this backend role, and anon/authenticated table grants are revoked.

Schema setup is performed separately via the connected Supabase account. Render sets TPP_EXTERNAL_SCHEMA=1; startup checks required tables with the runtime role, refuses to launch on failure and skips runtime DDL. Legacy deployments retain the original isolated schema tests.

The pooler endpoint was copied from the authenticated project connection panel. TLS uses verify-full and the official Supabase Root 2021 CA obtained from its authenticated database-settings certificate link. No passwords are committed. Admin login credentials were delivered privately to the owner.

This is a fresh database. Old Neon data remains untouched but has not been migrated because the source provider blocks access after quota exhaustion. Supplier VLESS/Xray profiles must be imported before issuing customer codes or testing carrier routing. App package and backend URL are unchanged by this database move.

## Live verification — 25 November 2026

Render deployment dep-dc3jl2cs6fmc73d8tnc0 (commit fd6ceaa9ad000efac09e5ed8b60ce41e4c31c6f4) reached live. The branded HTML, generated admin sign-in and authenticated database state were verified over HTTPS. The new database had zero customer accounts and zero supplier profiles at verification time.
Logout returned HTTP 200, and access to the admin state endpoint after logout correctly returned HTTP 401.
