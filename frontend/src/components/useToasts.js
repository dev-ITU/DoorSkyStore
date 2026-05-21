import { useCallback, useState } from 'react';

export function useToasts() {
  const [messages, setMessages] = useState([]);

  const dismiss = useCallback((id) => {
    setMessages((current) => current.filter((message) => message.id !== id));
  }, []);

  const push = useCallback(
    (text, type = 'success') => {
      const id = `${Date.now()}-${Math.random()}`;
      setMessages((current) => [{ id, text, type }, ...current].slice(0, 4));
      window.setTimeout(() => dismiss(id), 3500);
    },
    [dismiss],
  );

  return { messages, push, dismiss };
}
