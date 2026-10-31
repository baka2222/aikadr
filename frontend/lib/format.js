export function episodeCount(count) {
  const lastTwo = count % 100;
  const last = count % 10;
  const noun = lastTwo >= 11 && lastTwo <= 14 ? 'серий'
    : last === 1 ? 'серия' : last >= 2 && last <= 4 ? 'серии' : 'серий';
  return `${count} ${noun}`;
}
