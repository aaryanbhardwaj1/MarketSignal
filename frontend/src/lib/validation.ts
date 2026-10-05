/** Client-side mirrors of API input rules, for instant feedback. The API stays authoritative. */

export const WORKSPACE_CODE_PATTERN = /^[A-Z][A-Z0-9]{1,15}$/;
export const SOURCE_CODE_PATTERN = /^[A-Z0-9]{1,12}(-[A-Z0-9]{1,12}){0,5}$/;
export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".md", ".markdown", ".txt"];
export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

export function validateWorkspaceCode(code: string): string | null {
  if (!code) return "Code is required.";
  if (!WORKSPACE_CODE_PATTERN.test(code)) {
    return "2-16 characters: an uppercase letter followed by uppercase letters or digits.";
  }
  return null;
}

export function validateSourceCode(code: string): string | null {
  if (!code) return null;
  if (!SOURCE_CODE_PATTERN.test(code)) {
    return "Uppercase letters/digits in up to 6 hyphen-separated groups of 1-12 (e.g. Q3-REVIEW).";
  }
  return null;
}

export function validateUploadFile(file: File | null): string | null {
  if (!file) return "Choose a file to upload.";
  const lower = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    return `Unsupported file type. Accepted: ${ACCEPTED_EXTENSIONS.join(" ")}`;
  }
  if (file.size > MAX_UPLOAD_BYTES) return "File exceeds the 25 MB limit.";
  return null;
}
