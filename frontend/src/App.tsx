import { Header } from "./components/Header";
import { Footer } from "./components/Footer";
import { AuthModal } from "./components/AuthModal";
import { CartModal } from "./components/CartModal";
import { OrdersModal } from "./components/OrdersModal";
import { ToastHost } from "./components/ToastHost";
import { useEffect } from "react";
import { HomePage } from "./pages/HomePage";
import { MenuPage } from "./pages/MenuPage";
import { ProductPage } from "./pages/ProductPage";
import { useUI } from "./stores/ui";
import { useAuth } from "./stores/auth";

export default function App() {
  const view = useUI((s) => s.view);
  const modal = useUI((s) => s.modal);
  const viewKey = view.name === "product" ? `product-${view.id}` : view.name;

  // restore session on load
  useEffect(() => {
    useAuth.getState().refresh();
  }, []);

  return (
    <div className="flex min-h-dvh flex-col">
      <Header />
      <main key={viewKey} className="flex-1">
        {view.name === "home" && <HomePage />}
        {view.name === "menu" && <MenuPage />}
        {view.name === "product" && <ProductPage id={view.id} />}
      </main>
      <Footer />

      {modal === "auth" && <AuthModal />}
      {modal === "cart" && <CartModal />}
      {modal === "orders" && <OrdersModal />}
      <ToastHost />
    </div>
  );
}
