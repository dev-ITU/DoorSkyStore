import { useState } from 'react';

import { postForm } from '../lib/api.js';
import { money } from '../lib/format.js';
import { ToastStack } from './ToastStack.jsx';
import { useToasts } from './useToasts.js';

export function CartIsland({ catalogUrl, checkoutUrl, initialItems, subtotal, updateUrl }) {
  const [items, setItems] = useState(initialItems || []);
  const [cartSubtotal, setCartSubtotal] = useState(subtotal || 0);
  const [savingProductId, setSavingProductId] = useState(null);
  const { messages, push, dismiss } = useToasts();

  function clampQuantity(value, availableQuantity) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return 0;
    }
    return Math.min(Math.max(Math.trunc(parsed), 0), Number(availableQuantity || 0));
  }

  async function commitQuantity(productId, quantity) {
    setSavingProductId(productId);
    try {
      const data = await postForm(updateUrl, { product_id: productId, quantity });
      setItems((current) =>
        current.flatMap((item) => {
          const next = data.items.find((row) => Number(row.product_id) === Number(item.product.id));
          if (!next) {
            return [];
          }
          return [
            {
              ...item,
              available_quantity: next.available_quantity,
              quantity: next.quantity,
              line_total: next.line_total,
              unit_price: next.unit_price,
            },
          ];
        }),
      );
      setCartSubtotal(data.subtotal);
      push(data.message || 'Корзина обновлена.');
    } catch (error) {
      push(error.message, 'error');
    } finally {
      setSavingProductId(null);
    }
  }

  return (
    <section className="page-section">
      <ToastStack messages={messages} onDismiss={dismiss} />
      <div className="section-head">
        <h1>Корзина</h1>
        <a className="button ghost" href={catalogUrl}>
          Продолжить покупки
        </a>
      </div>

      {items.length ? (
        <>
          <div className="cart-list">
            {items.map((item) => {
              const saving = savingProductId === item.product.id;
              const itemQuantity = Number(item.quantity || 0);
              const unitPrice = Number(item.unit_price || 0);
              return (
                <article className="cart-row" key={item.product.id}>
                  <div>
                    <p className="eyebrow">
                      {item.product.sku} · {item.product.category_name}
                    </p>
                    <h2>
                      <a href={item.product.detail_url}>{item.product.name}</a>
                    </h2>
                    <p>Доступно: {item.available_quantity} шт.</p>
                  </div>
                  <div className="cart-controls">
                    <input
                      aria-label={`Количество ${item.product.name}`}
                      disabled={saving}
                      max={item.available_quantity}
                      min="0"
                      onChange={(event) => {
                        const quantity = clampQuantity(event.target.value, item.available_quantity);
                        setItems((current) =>
                          current.map((row) =>
                            row.product.id === item.product.id
                              ? {
                                  ...row,
                                  quantity,
                                  line_total: String(unitPrice * quantity),
                                }
                              : row,
                          ),
                        );
                      }}
                      onBlur={(event) => {
                        const quantity = clampQuantity(event.target.value, item.available_quantity);
                        commitQuantity(item.product.id, quantity);
                      }}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          event.preventDefault();
                          event.currentTarget.blur();
                        }
                      }}
                      type="number"
                      value={itemQuantity}
                    />
                    <strong>{money(item.line_total)}</strong>
                  </div>
                </article>
              );
            })}
          </div>
          <div className="cart-summary">
            <span>Итого</span>
            <strong>{money(cartSubtotal)}</strong>
            <a className="button primary" href={checkoutUrl}>
              Оформить заказ
            </a>
          </div>
        </>
      ) : (
        <p className="empty-state">В корзине пока нет товаров.</p>
      )}
    </section>
  );
}
