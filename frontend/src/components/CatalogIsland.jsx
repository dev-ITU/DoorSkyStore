import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

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

const INITIAL_QUERY = buildQuery(DEFAULT_FILTERS);

function ProductSkeletonGrid() {
  return (
    <div className="catalog-skeleton-grid" aria-hidden="true">
      {Array.from({ length: 6 }).map((_, index) => (
        <article className="catalog-skeleton-card" key={index}>
          <div className="catalog-skeleton-media" />
          <div className="catalog-skeleton-body">
            <span />
            <strong />
            <p />
            <em />
          </div>
        </article>
      ))}
    </div>
  );
}

export function CatalogIsland({
  addToCartUrl,
  apiUrl,
  categories,
  colors,
  initialNextUrl,
  initialProducts,
  materials,
  openingTypes,
}) {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [products, setProducts] = useState(initialProducts || []);
  const [nextUrl, setNextUrl] = useState(initialNextUrl || '');
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const firstRender = useRef(true);
  const loadingMoreRef = useRef(false);
  const sentinelRef = useRef(null);
  const { messages, push, dismiss } = useToasts();
  const query = useMemo(() => buildQuery(filters), [filters]);

  useEffect(() => {
    if (firstRender.current && query === INITIAL_QUERY) {
      firstRender.current = false;
      return undefined;
    }
    firstRender.current = false;

    const controller = new AbortController();
    setLoading(true);
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
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [apiUrl, query]);

  useEffect(() => {
    if (!nextUrl) {
      return undefined;
    }

    const prefetch = () => {
      fetchJson(nextUrl, { cacheTtl: 60000 }).catch(() => {});
    };
    if ('requestIdleCallback' in window) {
      const idleId = window.requestIdleCallback(prefetch, { timeout: 1600 });
      return () => window.cancelIdleCallback(idleId);
    }

    const timeoutId = window.setTimeout(prefetch, 450);
    return () => window.clearTimeout(timeoutId);
  }, [nextUrl]);

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  const loadMore = useCallback(async () => {
    if (!nextUrl || loading || loadingMoreRef.current) {
      return;
    }
    loadingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const data = await fetchJson(nextUrl);
      setProducts((current) => [...current, ...(data.results || [])]);
      setNextUrl(data.next || '');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }, [loading, nextUrl]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !nextUrl || typeof IntersectionObserver === 'undefined') {
      return undefined;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          loadMore();
        }
      },
      { rootMargin: '520px 0px 520px' },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore, nextUrl]);

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

      <section className={`catalog-results ${loading ? 'is-loading' : ''}`} aria-busy={loading}>
        <ToastStack messages={messages} onDismiss={dismiss} />
        {error ? <p className="empty-state">{error}</p> : null}
        {loading && products.length === 0 ? <ProductSkeletonGrid /> : null}
        {!loading && !error && products.length === 0 ? (
          <p className="empty-state">Подходящих товаров не найдено.</p>
        ) : null}
        {products.length > 0 ? (
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
        ) : null}
        <div className="catalog-autoload-sentinel" ref={sentinelRef} aria-live="polite">
          {loadingMore ? <span>Загрузка</span> : null}
        </div>
      </section>
    </section>
  );
}
