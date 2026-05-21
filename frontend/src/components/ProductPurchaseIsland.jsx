import { useEffect, useState } from 'react';

import { postForm } from '../lib/api.js';
import { money } from '../lib/format.js';
import { ToastStack } from './ToastStack.jsx';
import { useToasts } from './useToasts.js';

export function ProductPurchaseIsland({ addToCartUrl, product }) {
  const [saving, setSaving] = useState(false);
  const { messages, push, dismiss } = useToasts();
  const available = Number(product.available_quantity || 0);
  const initialCartQuantity = Number(product.cart_quantity || 0);
  const initialRemaining = Math.max(Number(product.remaining_quantity ?? available - initialCartQuantity), 0);
  const [cartQuantity, setCartQuantity] = useState(initialCartQuantity);
  const [quantity, setQuantity] = useState(initialRemaining > 0 ? 1 : 0);
  const remaining = Math.max(available - cartQuantity, 0);

  useEffect(() => {
    const nextCartQuantity = Number(product.cart_quantity || 0);
    const nextRemaining = Math.max(Number(product.remaining_quantity ?? available - nextCartQuantity), 0);
    setCartQuantity(nextCartQuantity);
    setQuantity(nextRemaining > 0 ? 1 : 0);
  }, [available, product.cart_quantity, product.id, product.remaining_quantity]);

  function clampQuantity(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return remaining > 0 ? 1 : 0;
    }
    return Math.min(Math.max(Math.trunc(parsed), 1), Math.max(remaining, 1));
  }

  async function addToCart(event) {
    event.preventDefault();
    if (remaining <= 0) {
      push('В корзине уже весь доступный остаток.', 'error');
      return;
    }

    const requestedQuantity = event.currentTarget.elements.quantity?.value ?? quantity;
    const safeQuantity = clampQuantity(requestedQuantity);
    setQuantity(safeQuantity);
    setSaving(true);
    try {
      const data = await postForm(addToCartUrl, {
        product_id: product.id,
        quantity: safeQuantity,
      });
      const nextCartQuantity = Number(data.cart_quantity ?? cartQuantity + safeQuantity);
      const nextRemaining = Number(data.remaining_quantity ?? Math.max(available - nextCartQuantity, 0));
      setCartQuantity(nextCartQuantity);
      setQuantity(nextRemaining > 0 ? 1 : 0);
      push(data.message || 'Товар добавлен в корзину.');
    } catch (error) {
      push(error.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <ToastStack messages={messages} onDismiss={dismiss} />
      <div className="purchase-panel">
        <strong>{money(product.price)}</strong>
        <span>Можно добавить: {remaining} шт.</span>
        <form className="add-cart-form" onSubmit={addToCart}>
          <input
            aria-label="Количество"
            disabled={remaining <= 0}
            max={Math.max(remaining, 1)}
            min="1"
            name="quantity"
            onChange={(event) => setQuantity(clampQuantity(event.target.value))}
            type="number"
            value={quantity}
          />
          <button className="button primary" disabled={saving || remaining <= 0} type="submit">
            {saving ? '...' : 'Добавить в корзину'}
          </button>
        </form>
      </div>
    </>
  );
}
