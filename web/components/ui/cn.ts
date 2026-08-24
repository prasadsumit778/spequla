/** Join class names, dropping falsey entries. The whole of our styling
 *  utility layer -- there is no design system to build here (CLAUDE.md
 *  section 6). */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
