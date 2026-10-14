/** CLB/NCLC range label: conversion tables start at level 4, so anything lower shows as "<4". */
export function levelRange(low: number | null, high: number | null): string {
  if (low === null || high === null) return "–";
  const show = (n: number) => (n < 4 ? "<4" : String(n));
  return low === high ? show(low) : `${show(low)}–${show(high)}`;
}
