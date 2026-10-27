/**
 * Cultivar counts derived from the /query/plant/summary payload.
 *
 * The endpoint reports one cultivar count and it is "cultivars with at least
 * one plant" (database_stats_service.py: count(distinct plants.cultivar_id)),
 * which is smaller than the catalogue. The catalogue total is not in the
 * payload, but every cultivar_breakdowns entry groups the whole cultivars
 * table, so each one sums to it. Three independent group-bys must agree: if
 * they do not, the assumption behind this derivation no longer holds and the
 * catalogue total is reported as null rather than guessed at.
 *
 * Kept in step with CULTIVAR_BREAKDOWN_COLUMNS in
 * backend/app/services/database_stats_service.py.
 */
const BREAKDOWN_KEYS = ['genome_type', 'common_name', 'manufacturer_name'];

export const deriveCultivarCounts = (summary) => {
    const breakdowns = summary?.cultivar_breakdowns;
    const imaged = summary?.total_cultivars ?? null;
    if (!breakdowns) return { imaged, catalogued: null };

    const totals = BREAKDOWN_KEYS
        .map((name) => breakdowns[name])
        .filter(Boolean)
        .map((counts) => Object.values(counts).reduce((a, b) => a + b, 0));

    const agreed = totals.length === BREAKDOWN_KEYS.length
        && totals.every((t) => t === totals[0]);

    return { imaged, catalogued: agreed ? totals[0] : null };
};
