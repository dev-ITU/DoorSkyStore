export function ToastStack({ messages, onDismiss }) {
  if (!messages.length) {
    return null;
  }

  return (
    <div className="island-toast-stack" role="status" aria-live="polite">
      {messages.map((message) => (
        <button
          className={`message message-${message.type}`}
          key={message.id}
          type="button"
          onClick={() => onDismiss(message.id)}
        >
          {message.text}
        </button>
      ))}
    </div>
  );
}
