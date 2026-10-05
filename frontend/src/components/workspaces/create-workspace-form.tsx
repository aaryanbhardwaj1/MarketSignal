"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { createWorkspace } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { Workspace } from "@/lib/api/types";
import { validateWorkspaceCode } from "@/lib/validation";
import { InlineError } from "../ui/error-panel";
import { buttonClass, Field, TextInput } from "../ui/form-controls";

export function CreateWorkspaceForm() {
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [touched, setTouched] = useState(false);
  const [created, setCreated] = useState<Workspace | null>(null);

  const codeError = validateWorkspaceCode(code);
  const nameError = name.trim() ? null : "Name is required.";

  const mutation = useMutation({
    mutationFn: createWorkspace,
    onSuccess: (workspace) => {
      setCreated(workspace);
      setCode("");
      setName("");
      setDescription("");
      setTouched(false);
      void queryClient.invalidateQueries({ queryKey: queryKeys.workspaces });
    },
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    setCreated(null);
    if (codeError || nameError) return;
    mutation.mutate({
      code,
      name: name.trim(),
      description: description.trim() || undefined,
    });
  };

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <Field
        id="ws-code"
        label="Code"
        hint="Uppercase, e.g. NORTHSTAR. Used in every evidence handle; cannot change."
        error={touched ? codeError : null}
      >
        <TextInput
          id="ws-code"
          value={code}
          maxLength={16}
          autoComplete="off"
          aria-invalid={touched && !!codeError}
          aria-describedby={touched && codeError ? "ws-code-error" : "ws-code-hint"}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          className="font-mono"
        />
      </Field>
      <Field id="ws-name" label="Name" error={touched ? nameError : null}>
        <TextInput
          id="ws-name"
          value={name}
          aria-invalid={touched && !!nameError}
          aria-describedby={touched && nameError ? "ws-name-error" : undefined}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <Field id="ws-description" label="Description (optional)">
        <TextInput
          id="ws-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </Field>
      {mutation.error && <InlineError error={mutation.error} />}
      {created && (
        <p role="status" className="text-sm text-emerald-700">
          Created{" "}
          <Link className="font-medium underline" href={`/w/${encodeURIComponent(created.code)}`}>
            {created.code}
          </Link>
          .
        </p>
      )}
      <div>
        <button type="submit" className={buttonClass("primary")} disabled={mutation.isPending}>
          {mutation.isPending ? "Creating..." : "Create workspace"}
        </button>
      </div>
    </form>
  );
}
