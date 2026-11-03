export function isVisibleDiff(row) {
  return row?.type !== "same" && row?.current !== row?.backup;
}

export function diffGroupsFromIndexes(indexes) {
  const groups = [];
  for (const index of indexes) {
    const last = groups[groups.length - 1];
    if (last && index <= last.end + 1) {
      last.end = index;
    } else {
      groups.push({ start: index, end: index });
    }
  }
  return groups;
}

export function nextDiffIndex(diffGroups, activeDiffIndex, direction) {
  if (!diffGroups.length) return null;
  const currentPosition = diffGroups.findIndex((group) => activeDiffIndex >= group.start && activeDiffIndex <= group.end);
  const nextPosition = currentPosition === -1
    ? 0
    : (currentPosition + direction + diffGroups.length) % diffGroups.length;
  return diffGroups[nextPosition].start;
}
