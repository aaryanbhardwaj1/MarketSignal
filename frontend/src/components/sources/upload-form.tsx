"use client";

import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { uploadSource } from "@/lib/api/endpoints";
import {
  CONFIDENTIALITY_LEVELS,
  SOURCE_CLASSES,
  type Confidentiality,
  type SourceClass,
  type UploadSourceInput,
} from "@/lib/api/types";
import { ACCEPTED_EXTENSIONS, validateSourceCode, validateUploadFile } from "@/lib/validation";
import { InlineError } from "../ui/error-panel";
import { buttonClass, Field, Select, TextInput } from "../ui/form-controls";
import { UploadResultMessage } from "./upload-result";

export function UploadForm({ ws, onUploaded }: { ws: string; onUploaded: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [sourceClass, setSourceClass] = useState<SourceClass>("internal");
  const [confidentiality, setConfidentiality] = useState<Confidentiality>("internal");
  const [title, setTitle] = useState("");
  const [sourceCode, setSourceCode] = useState("");
  const [touched, setTouched] = useState(false);

  const fileError = validateUploadFile(file);
  const codeError = validateSourceCode(sourceCode);

  const mutation = useMutation({
    mutationFn: (input: UploadSourceInput) => uploadSource(ws, input),
    onSuccess: () => {
      setFile(null);
      setFileInputKey((k) => k + 1);
      setTitle("");
      setSourceCode("");
      setTouched(false);
      onUploaded();
    },
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (fileError || codeError || !file) return;
    mutation.mutate({
      file,
      source_class: sourceClass,
      confidentiality,
      title: title.trim() || undefined,
      source_code: sourceCode || undefined,
    });
  };

  return (
    <form onSubmit={onSubmit} noValidate className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
      <div className="md:col-span-2">
        <Field
          id="upload-file"
          label="File"
          hint={`${ACCEPTED_EXTENSIONS.join(" ")} - max 25 MB`}
          error={touched ? fileError : null}
        >
          <input
            key={fileInputKey}
            id="upload-file"
            type="file"
            accept={ACCEPTED_EXTENSIONS.join(",")}
            aria-invalid={touched && !!fileError}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-slate-700 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-slate-800 hover:file:bg-slate-200"
          />
        </Field>
      </div>
      <Field id="upload-class" label="Source class">
        <Select
          id="upload-class"
          value={sourceClass}
          onChange={(e) => setSourceClass(e.target.value as SourceClass)}
        >
          {SOURCE_CLASSES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
      </Field>
      <Field id="upload-confidentiality" label="Confidentiality">
        <Select
          id="upload-confidentiality"
          value={confidentiality}
          onChange={(e) => setConfidentiality(e.target.value as Confidentiality)}
        >
          {CONFIDENTIALITY_LEVELS.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
      </Field>
      <Field id="upload-title" label="Title (optional)">
        <TextInput id="upload-title" value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field
        id="upload-code"
        label="Source code (optional)"
        hint="e.g. Q3-REVIEW"
        error={touched ? codeError : null}
      >
        <TextInput
          id="upload-code"
          value={sourceCode}
          className="font-mono"
          aria-invalid={touched && !!codeError}
          onChange={(e) => setSourceCode(e.target.value.toUpperCase())}
        />
      </Field>
      <div className="flex flex-col gap-3 md:col-span-2 xl:col-span-6">
        {mutation.error && <InlineError error={mutation.error} />}
        {mutation.data && <UploadResultMessage ws={ws} result={mutation.data} />}
        <div>
          <button type="submit" className={buttonClass("primary")} disabled={mutation.isPending}>
            {mutation.isPending ? "Uploading..." : "Upload source"}
          </button>
        </div>
      </div>
    </form>
  );
}
