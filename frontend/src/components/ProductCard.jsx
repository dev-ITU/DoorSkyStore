import { useEffect, useState } from 'react';

import { postForm } from '../lib/api.js';
import { money } from '../lib/format.js';

export function ProductCard({ product, addToCartUrl, onToast }) {
  const imageUrl = product.display_image || '';
  const available = Number(product.available_quantity || 0);
  const initialCartQuantity = Number(product.cart_quantity || 0);
  const initialRemaining = Math.max(Number(product.remaining_quantity ?? available - initialCartQuantity), 0);
  const [cartQuantity, setCartQuantity] = useState(initialCartQuantity);
  const [quantity, setQuantity] = useState(initialRemaining > 0 ? 1 : 0);
  const [saving, setSaving] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(!imageUrl);
  const remaining = Math.max(available - cartQuantity, 0);
  const disabled = remaining <= 0 || saving;

  useEffect(() => {
    setImageLoaded(!imageUrl);
  }, [imageUrl]);

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

  async function handleSubmit(event) {
    event.preventDefault();
    if (remaining <= 0) {
      onToast('В корзине уже весь доступный остаток.', 'error');
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
      onToast(data.message || 'Товар добавлен в корзину.');
    } catch (error) {
      onToast(error.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="product-card">
      <a className={`product-image ${imageUrl && !imageLoaded ? 'is-loading' : ''}`} href={product.detail_url}>
        {imageUrl ? (
          <img
            alt={product.name}
            className={imageLoaded ? 'is-loaded' : ''}
            data-lazy-image
            decoding="async"
            fetchPriority="low"
            loading="lazy"
            onError={() => setImageLoaded(true)}
            onLoad={() => setImageLoaded(true)}
            src={imageUrl}
          />
        ) : (
          <span>{product.category.name}</span>
        )}
        <span className={`stock-badge ${available > 0 ? 'is-available' : 'is-empty'}`}>
          {available > 0 ? 'В наличии' : 'Под заказ'}
        </span>
      </a>
      <div className="product-card-body">
        <p className="eyebrow">{product.category.name}</p>
        <h2>
          <a href={product.detail_url}>{product.name}</a>
        </h2>
        <div className="product-actions">
          <p>
            {[product.material, product.color, product.finish].filter(Boolean).join(' · ')}
          </p>
          <div className="product-meta">
            <strong>{money(product.price)}</strong>
            <span>{remaining} шт. можно добавить</span>
          </div>
          <form className="add-cart-form" onSubmit={handleSubmit}>
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
            <button className="button primary" disabled={disabled} type="submit">
              {saving ? '...' : 'В корзину'}
            </button>
          </form>
        </div>
      </div>
    </article>
  );
}
