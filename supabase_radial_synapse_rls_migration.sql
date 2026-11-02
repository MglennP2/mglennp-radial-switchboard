BEGIN;
CREATE TABLE IF NOT EXISTS public.radial_synapse_agents (
    agent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    agent_slug TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    endpoint_url TEXT NOT NULL,
    mcp_or_a2a_card_url TEXT,
    source_registry TEXT NOT NULL DEFAULT 'mcp_registry',
    mgle_nnp_code CHAR(8) NOT NULL DEFAULT '1CCBBZES',
    fingerprint_64bit BIGINT NOT NULL,
    domain_bits_16 INT NOT NULL DEFAULT 0,
    hop_ttl SMALLINT NOT NULL DEFAULT 0 CHECK (hop_ttl BETWEEN 0 AND 15),
    schema_version SMALLINT NOT NULL DEFAULT 1,
    merit_grade CHAR(1) NOT NULL DEFAULT 'C' CHECK (merit_grade IN ('A','B','C','D','E','F')),
    guarantee_grade CHAR(1) NOT NULL DEFAULT 'C' CHECK (guarantee_grade IN ('A','B','C','D','E','F')),
    latency_grade CHAR(1) NOT NULL DEFAULT 'B' CHECK (latency_grade IN ('A','B','C','D','E','F')),
    economy_grade CHAR(1) NOT NULL DEFAULT 'B' CHECK (economy_grade IN ('A','B','C','D','F')),
    node_behavior CHAR(1) NOT NULL DEFAULT 'Z' CHECK (node_behavior IN ('Z','S','B','A','H')),
    neighborhood_region CHAR(1) NOT NULL DEFAULT 'E' CHECK (neighborhood_region IN ('E','C','W','U','A','G')),
    preference_socket CHAR(1) NOT NULL DEFAULT 'S' CHECK (preference_socket IN ('S','N','C','D','M')),
    hebbian_resonance_weight NUMERIC(5,2) NOT NULL DEFAULT 1.00 CHECK (hebbian_resonance_weight BETWEEN 0.00 AND 5.00),
    verified_handshakes_count BIGINT NOT NULL DEFAULT 0,
    anti_subcontracting_canary_passed BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_probed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.radial_synapse_agents ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read active non-blacklisted MGLE-NNP agents" ON public.radial_synapse_agents;
DROP POLICY IF EXISTS "Switchboard service_role full directory access" ON public.radial_synapse_agents;
CREATE POLICY "Switchboard service_role full directory access"
    ON public.radial_synapse_agents FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);
DROP POLICY IF EXISTS "Developers can view own registered agents" ON public.radial_synapse_agents;
CREATE POLICY "Developers can view own registered agents"
    ON public.radial_synapse_agents FOR SELECT TO authenticated USING (auth.uid() = owner_id);
CREATE OR REPLACE VIEW public.radial_switchboard_public_stats
WITH (security_invoker = false)
AS
SELECT
    COUNT(*)::BIGINT AS total_indexed_agents,
    COUNT(*) FILTER (WHERE guarantee_grade IN ('A', 'B') AND is_active = TRUE)::BIGINT AS verified_live_callable_ab,
    COUNT(*) FILTER (WHERE guarantee_grade = 'E')::BIGINT AS quarantined_dead_grade_e,
    COUNT(*) FILTER (WHERE guarantee_grade = 'D')::BIGINT AS unhosted_repos_grade_d,
    MAX(last_probed_at) AS last_global_crawl_utc
FROM public.radial_synapse_agents;
GRANT SELECT ON public.radial_switchboard_public_stats TO anon, authenticated, service_role;
COMMIT;
