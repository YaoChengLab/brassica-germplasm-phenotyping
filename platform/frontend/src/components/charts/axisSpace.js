// Recharts reserves a fixed 60 px for a YAxis, and an axis title placed with
// position="insideLeft" is drawn inside that same band — so as soon as the tick
// labels get wide (leaf area in pixels runs to six digits) the title and the numbers
// are drawn on top of each other. Nothing in recharts measures this for us.
//
// Two pieces, used together:
//   yTickWidth()  sizes the axis band to the tick text it will actually render
//   yAxisTitle    puts the title in its own flex column beside the chart, so it can
//                 never share space with the ticks whatever their width
//
// Widths are estimated, not measured: for the digit-and-separator strings on a
// numeric axis, character width is a stable fraction of the font size, so a
// per-character estimate is accurate enough and costs no layout pass. Verify changes
// here with a headless render that compares the rendered tick and title rectangles.

const DIGIT_WIDTH_RATIO = 0.62; // digits in the default sans stack
const TICK_GAP = 12; // recharts' tick line plus a little air

/**
 * Width a vertical axis needs for its tick labels alone (no title inside).
 *
 * @param values       numbers the axis will show; the widest one wins
 * @param fontSize     tick label font size, px
 * @param format       tick formatter — must be the chart's tickFormatter
 * @param extraChars   headroom for recharts rounding the top tick up a digit
 */
export const yTickWidth = ({
  values,
  fontSize = 16,
  format = (v) => (v == null ? '' : String(v)),
  extraChars = 1,
}) => {
  const widest = (values || [])
    .filter((v) => v != null && isFinite(v))
    .map((v) => format(v).length)
    .reduce((a, b) => Math.max(a, b), 1);
  return Math.ceil((widest + extraChars) * fontSize * DIGIT_WIDTH_RATIO) + TICK_GAP;
};

/**
 * Style for a rotated axis title rendered as a sibling of the chart, e.g.
 *   <div style={{ display: 'flex' }}>
 *     <div style={yAxisTitleStyle()}>Leaf area (px)</div>
 *     <ResponsiveContainer>…</ResponsiveContainer>
 *   </div>
 * The chart's own vertical centre and the plot area's centre coincide closely
 * enough (top legend ≈ bottom axis band), so no manual centring is needed.
 */
export const yAxisTitleStyle = (fontSize = 16, { before = 0, after = 6 } = {}) => ({
  writingMode: 'vertical-rl',
  transform: 'rotate(180deg)',
  fontSize,
  color: '#666',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  flex: '0 0 auto',
  whiteSpace: 'nowrap',
  // Charts stacked in one column share an axis band width so their plot areas line
  // up. The chart whose numbers are narrower has slack to give away: it goes in
  // `before` (outside the title), so the title still sits right next to its own
  // ticks. Putting it in `after` would leave the title stranded to the left.
  marginLeft: before,
  marginRight: after,
});
