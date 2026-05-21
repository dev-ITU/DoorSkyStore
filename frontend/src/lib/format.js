export function money(value) {
  return `${new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 0,
  }).format(Number(value || 0))} руб.`;
}
