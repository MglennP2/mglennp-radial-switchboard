BEGIN;


ALTER TABLE IF EXISTS public.radial_agent_phonebook
    ADD COLUMN IF NOT EXISTS auth_mode TEXT NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS rate_limit_rpm INTEGER,
    ADD COLUMN IF NOT EXISTS poison_scan_clean BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS encounter_count INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS room_completions INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS room_failures INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dossier_json JSONB NOT NULL DEFAULT '{}'::jsonb;


CREATE INDEX IF NOT EXISTS idx_radial_phonebook_guarantee
    ON public.radial_agent_phonebook (guarantee_grade);


CREATE INDEX IF NOT EXISTS idx_radial_phonebook_u64
    ON public.radial_agent_phonebook (mgle_nnp_64bit);


CREATE TABLE IF NOT EXISTS public.radial_tax_revenue_ledger (
    entry_id TEXT PRIMARY KEY,
    received_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    network TEXT NOT NULL DEFAULT 'eip155:8453',
    treasury_wallet TEXT NOT NULL DEFAULT '0x24b1a09b489c67c3e43f7cd1f3023aef544104fd',
    payer_wallet TEXT NOT NULL,
    tx_hash TEXT NOT NULL UNIQUE,
    gross_usdc_received NUMERIC(18, 6) NOT NULL,
    fair_market_value_usd NUMERIC(18, 6) NOT NULL,
    irs_schedule_c_classification TEXT NOT NULL DEFAULT 'Ordinary Business Service Income (USDC at Receipt FMV)',
    tax_reserve_30pct_usd NUMERIC(18, 6) NOT NULL,
    operating_cash_60pct_usd NUMERIC(18, 6) NOT NULL,
    post_tax_treasury_slice_10pct_usd NUMERIC(18, 6) NOT NULL,
    handshakes_issued INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


ALTER TABLE public.radial_tax_revenue_ledger ENABLE ROW LEVEL SECURITY;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'radial_tax_revenue_ledger'
          AND policyname = 'service_role_only_tax_ledger'
    ) THEN
        CREATE POLICY service_role_only_tax_ledger
            ON public.radial_tax_revenue_ledger
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true);
    END IF;
END
$$;


COMMIT;
