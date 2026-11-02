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
    constructive_status_note TEXT NOT NULL DEFAULT 'Verified on Virginia heartbeat check.',
    anti_subcontracting_canary_passed BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_probed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS public.radial_agent_appeals (
    appeal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_slug TEXT NOT NULL REFERENCES public.radial_synapse_agents(agent_slug) ON DELETE CASCADE,
    appellant_name_or_handle TEXT NOT NULL CHECK (char_length(appellant_name_or_handle) BETWEEN 2 AND 80),
    appeal_category TEXT NOT NULL DEFAULT 'RE_AUDIT_REQUEST' CHECK (
        appeal_category IN ('RE_AUDIT_REQUEST', 'GRADE_DISAGREEMENT', 'UPDATED_ENDPOINT_URL', 'OUTSIDE_THIRD_PARTY_AUDIT')
    ),
    proposed_endpoint_url TEXT,
    reason_and_evidence TEXT NOT NULL CHECK (char_length(reason_and_evidence) BETWEEN 10 AND 1200),
    audit_status TEXT NOT NULL DEFAULT 'PENDING_LIVE_REAUDIT' CHECK (
        audit_status IN ('PENDING_LIVE_REAUDIT', 'RETESTED_AND_UPGRADED', 'UNDER_COMMUNITY_REVIEW', 'RESOLVED_WITH_NOTE')
    ),
    switchboard_resolution_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS public.radial_agent_comments (
    comment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_slug TEXT NOT NULL REFERENCES public.radial_synapse_agents(agent_slug) ON DELETE CASCADE,
    author_display_name TEXT NOT NULL CHECK (char_length(author_display_name) BETWEEN 2 AND 60),
    feedback_type TEXT NOT NULL DEFAULT 'REAL_USER_FEEDBACK' CHECK (
        feedback_type IN ('REAL_USER_FEEDBACK', 'QUESTION_OR_DISAGREEMENT', 'CREATOR_NOTE', 'OUTSIDE_AUDIT_VERIFICATION')
    ),
    worked_as_expected BOOLEAN NOT NULL DEFAULT TRUE,
    observed_latency_ms INT CHECK (observed_latency_ms IS NULL OR observed_latency_ms BETWEEN 1 AND 60000),
    comment_body TEXT NOT NULL CHECK (char_length(comment_body) BETWEEN 5 AND 1000),
    helpful_upvotes INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


ALTER TABLE public.radial_synapse_agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.radial_agent_appeals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.radial_agent_comments ENABLE ROW LEVEL SECURITY;


DROP POLICY IF EXISTS "Public transparent read of rated agents" ON public.radial_synapse_agents;
CREATE POLICY "Public transparent read of rated agents"
    ON public.radial_synapse_agents FOR SELECT TO anon, authenticated USING (is_active = TRUE);


DROP POLICY IF EXISTS "Switchboard service_role full directory access" ON public.radial_synapse_agents;
CREATE POLICY "Switchboard service_role full directory access"
    ON public.radial_synapse_agents FOR ALL TO service_role USING (TRUE) WITH CHECK (TRUE);


DROP POLICY IF EXISTS "Public read agent appeals and outside audits" ON public.radial_agent_appeals;
CREATE POLICY "Public read agent appeals and outside audits"
    ON public.radial_agent_appeals FOR SELECT TO anon, authenticated USING (TRUE);


DROP POLICY IF EXISTS "Public submit constructive appeal or re-audit" ON public.radial_agent_appeals;
CREATE POLICY "Public submit constructive appeal or re-audit"
    ON public.radial_agent_appeals FOR INSERT TO anon, authenticated
    WITH CHECK (audit_status = 'PENDING_LIVE_REAUDIT' AND char_length(reason_and_evidence) BETWEEN 10 AND 1200);


DROP POLICY IF EXISTS "Public read per-agent comments and feedback" ON public.radial_agent_comments;
CREATE POLICY "Public read per-agent comments and feedback"
    ON public.radial_agent_comments FOR SELECT TO anon, authenticated USING (TRUE);


DROP POLICY IF EXISTS "Public post constructive agent comment or feedback" ON public.radial_agent_comments;
CREATE POLICY "Public post constructive agent comment or feedback"
    ON public.radial_agent_comments FOR INSERT TO anon, authenticated
    WITH CHECK (helpful_upvotes = 0 AND char_length(comment_body) BETWEEN 5 AND 1000);


COMMIT;
