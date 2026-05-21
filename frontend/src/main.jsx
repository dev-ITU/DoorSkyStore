import { createRoot } from 'react-dom/client';

import { CartIsland } from './components/CartIsland.jsx';
import { CatalogIsland } from './components/CatalogIsland.jsx';
import { ProductPurchaseIsland } from './components/ProductPurchaseIsland.jsx';

const ISLANDS = {
  cart: CartIsland,
  catalog: CatalogIsland,
  productPurchase: ProductPurchaseIsland,
};

function propsFor(root) {
  const propsId = root.dataset.propsId;
  if (!propsId) {
    return {};
  }
  const script = document.getElementById(propsId);
  if (!script) {
    return {};
  }
  return JSON.parse(script.textContent || '{}');
}

document.querySelectorAll('[data-react-island]').forEach((root) => {
  const Component = ISLANDS[root.dataset.reactIsland];
  if (!Component) {
    return;
  }
  createRoot(root).render(<Component {...propsFor(root)} />);
});
