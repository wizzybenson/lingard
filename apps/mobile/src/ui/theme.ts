export const colors = {
  ink: "#1d2433",
  paper: "#fbf8f2",
  muted: "#6b7280",
  accent: "#2f6fab",
  accentInk: "#ffffff",
  danger: "#b42318",
  success: "#1f7a4d",
  card: "#ffffff",
  border: "#e5e1d8",
} as const;

export const space = (n: number): number => n * 8;
