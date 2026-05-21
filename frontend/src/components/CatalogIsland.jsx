import { useEffect, useMemo, useState } from 'react';

import { fetchJson } from '../lib/api.js';
import { ProductCard } from './ProductCard.jsx';
import { ToastStack } from './ToastStack.jsx';
import { useToasts } from './useToasts.js';

const DEFAULT_FILTERS = {
  q: '',
  category: '',
  opening_type: '',
  material: '',
  color: '',
  min_price: '',
  max_price: '',
  in_stock: false,
  ordering: 'name',
};

function buildQuery(filters) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (key === 'in_stock') {
      if (value) {
        params.set(key, '1');
      }
      return;
    }
    if (value !== '') {
      params.set(key, value);
    }
  });
  return params.toString();
}

export function CatalogIsland({
  addToCartUrl,
  apiUrl,
  categories,
  colors,
  initialProducts,
  materials,
  openingTypes,
}) {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [products, setProducts] = useState(initialProducts || []);
  const [nextUrl, setNextUrl] = useState('');
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const { messages, push, dismiss } = useToasts();
  const query = useMemo(() => buildQuery(filters), [filters]);

  useEffect(() => {
    const controller = new AbortController();
    setError('');

    fetchJson(`${apiUrl}?${query}`, { signal: controller.signal })
      .then((data) => {
        setProducts(data.results || []);
        setNextUrl(data.next || '');
      })
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') {
          setError(requestError.message);
        }
      })

    return () => controller.abort();
  }, [apiUrl, query]);

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  async function loadMore() {
    if (!nextUrl) {
      return;
    }
    setLoadingMore(true);
    try {
      const data = await fetchJson(nextUrl);
      setProducts((current) => [...current, ...(data.results || [])]);
      setNextUrl(data.next || '');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <section className="catalog-layout">
      <aside className="filters">
        <h1>Каталог дверей</h1>
        <details className="filter-panel">
          <summary>
            <span>Фильтры</span>
            <span className="filter-toggle-icon" aria-hidden="true" />
          </summary>
          <form className="filter-form" onSubmit={(event) => event.preventDefault()}>
            <label>
              Поиск
              <input
                name="q"
                onChange={(event) => updateFilter('q', event.target.value)}
                placeholder="Название, артикул, отделка"
                type="search"
                value={filters.q}
              />
            </label>
            <label>
              Категория
              <select
                name="category"
                onChange={(event) => updateFilter('category', event.target.value)}
                value={filters.category}
              >
                <option value="">Все категории</option>
                {categories.map((category) => (
                  <option key={category.slug} value={category.slug}>
                    {category.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Тип открывания
              <select
                name="opening_type"
                onChange={(event) => updateFilter('opening_type', event.target.value)}
                value={filters.opening_type}
              >
                <option value="">Любой</option>
                {openingTypes.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Материал
              <select
                name="material"
                onChange={(event) => updateFilter('material', event.target.value)}
                value={filters.material}
              >
                <option value="">Любой</option>
                {materials.map((material) => (
                  <option key={material} value={material}>
                    {material}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Цвет
              <select
                name="color"
                onChange={(event) => updateFilter('color', event.target.value)}
                value={filters.color}
              >
                <option value="">Любой</option>
                {colors.map((color) => (
                  <option key={color} value={color}>
                    {color}
                  </option>
                ))}
              </select>
            </label>
            <div className="price-row">
              <label>
                Цена от
                <input
                  min="0"
                  name="min_price"
                  onChange={(event) => updateFilter('min_price', event.target.value)}
                  step="1000"
                  type="number"
                  value={filters.min_price}
                />
              </label>
              <label>
                Цена до
                <input
                  min="0"
                  name="max_price"
                  onChange={(event) => updateFilter('max_price', event.target.value)}
                  step="1000"
                  type="number"
                  value={filters.max_price}
                />
              </label>
            </div>
            <label className="check-row">
              <input
                checked={filters.in_stock}
                name="in_stock"
                onChange={(event) => updateFilter('in_stock', event.target.checked)}
                type="checkbox"
                value="1"
              />
              Только в наличии
            </label>
            <label>
              Сортировка
              <select
                name="ordering"
                onChange={(event) => updateFilter('ordering', event.target.value)}
                value={filters.ordering}
              >
                <option value="name">По названию</option>
                <option value="price">Цена по возрастанию</option>
                <option value="-price">Цена по убыванию</option>
                <option value="-created_at">Новые сначала</option>
              </select>
            </label>
          </form>
        </details>
      </aside>

      <section className="catalog-results">
        <ToastStack messages={messages} onDismiss={dismiss} />
        {error ? <p className="empty-state">{error}</p> : null}
        {!error && products.length === 0 ? (
          <p className="empty-state">Подходящих товаров не найдено.</p>
        ) : (
          <div className="product-grid">
            {products.map((product) => (
              <ProductCard
                addToCartUrl={addToCartUrl}
                key={product.id}
                onToast={push}
                product={product}
              />
            ))}
          </div>
        )}
        {nextUrl ? (
          <div className="load-more-row">
            <button className="button ghost" disabled={loadingMore} onClick={loadMore} type="button">
              {loadingMore ? 'Загрузка...' : 'Показать еще'}
            </button>
          </div>
        ) : null}
      </section>
    </section>
  );
}
