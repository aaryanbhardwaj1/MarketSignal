"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";

type Listener = () => void;

interface NewChatSignal {
  subscribe: (listener: Listener) => () => void;
  emit: () => void;
}

const NOOP_SIGNAL: NewChatSignal = { subscribe: () => () => {}, emit: () => {} };

const NewChatContext = createContext<NewChatSignal>(NOOP_SIGNAL);

/** Shell-level channel for "New chat" presses; mounted once by the app shell. */
export function NewChatSignalProvider({ children }: { children: ReactNode }) {
  const listeners = useRef(new Set<Listener>());
  const subscribe = useCallback((listener: Listener) => {
    listeners.current.add(listener);
    return () => {
      listeners.current.delete(listener);
    };
  }, []);
  const emit = useCallback(() => {
    for (const listener of [...listeners.current]) listener();
  }, []);
  const value = useMemo(() => ({ subscribe, emit }), [subscribe, emit]);
  return <NewChatContext.Provider value={value}>{children}</NewChatContext.Provider>;
}

/**
 * Runs `onNewChat` whenever someone presses "New chat" in the shell (sidebar or rail), including
 * when they are already on the empty Chat page. Chat uses it to clear the composer draft and
 * focus it. The latest callback is always used; no re-subscription needed when it changes.
 */
export function useNewChatSignal(onNewChat: () => void): void {
  const { subscribe } = useContext(NewChatContext);
  const latest = useRef(onNewChat);
  useEffect(() => {
    latest.current = onNewChat;
  });
  useEffect(() => subscribe(() => latest.current()), [subscribe]);
}

/** The emitter used by the shell's "New chat" controls. */
export function useEmitNewChat(): () => void {
  return useContext(NewChatContext).emit;
}
