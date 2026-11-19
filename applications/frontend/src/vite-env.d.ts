/// <reference types="vite/client" />

// Vite handles these imports, but `tsc --noEmit` needs an explicit declaration.
// TypeScript 5.9 reports TS2882 for side-effect imports without one.
declare module "*.css";
declare module "*.scss";
declare module "*.svg" {
  const content: string;
  export default content;
}
declare module "*.png" {
  const content: string;
  export default content;
}
