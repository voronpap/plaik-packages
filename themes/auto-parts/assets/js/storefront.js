(function () {
  "use strict";

  var csrfToken = null;
  var queryCache = Object.create(null);

  function idempotencyKey() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }

    if (window.crypto && typeof window.crypto.getRandomValues === "function") {
      var bytes = new Uint8Array(24);
      window.crypto.getRandomValues(bytes);
      return Array.prototype.map.call(bytes, function (value) {
        return value.toString(16).padStart(2, "0");
      }).join("");
    }

    throw new Error("Secure browser randomness is unavailable.");
  }

  async function publicQuery(packageId, queryId, payload) {
    var key = packageId + ":" + queryId + ":" + JSON.stringify(payload);

    if (!queryCache[key]) {
      queryCache[key] = fetch(
        "/api/storefront/" + packageId + "/queries/" + queryId,
        {
          method: "POST",
          credentials: "same-origin",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        }
      ).then(async function (response) {
        if (!response.ok) {
          throw new Error("Public storefront query failed.");
        }

        var body = await response.json();
        return body && body.data ? body.data : {};
      });
    }

    return queryCache[key];
  }

  function formatMoney(amountMinor, currency) {
    try {
      return new Intl.NumberFormat("uk-UA", {
        style: "currency",
        currency: currency || "UAH"
      }).format(Number(amountMinor) / 100);
    } catch (_) {
      return (Number(amountMinor) / 100).toFixed(2) + " " + (currency || "UAH");
    }
  }

  function hydratePrice(element) {
    var productId = element.dataset.productId;
    if (!productId) return;

    publicQuery("pricing", "price", {product_id: productId})
      .then(function (data) {
        if (
          typeof data.amount_minor !== "number" ||
          typeof data.currency !== "string"
        ) {
          throw new Error("Price unavailable.");
        }

        element.textContent = formatMoney(data.amount_minor, data.currency);
        element.dataset.state = "ready";
      })
      .catch(function () {
        element.textContent = "Ціна недоступна";
        element.dataset.state = "error";
      });
  }

  function hydrateAvailability(element) {
    var productId = element.dataset.productId;
    if (!productId) return;

    publicQuery("inventory", "availability", {product_id: productId})
      .then(function (data) {
        var quantity = Number(data.quantity);

        if (!Number.isFinite(quantity)) {
          throw new Error("Availability unavailable.");
        }

        if (quantity > 0) {
          element.textContent = "В наявності: " + quantity + " шт.";
          element.dataset.state = "in-stock";
        } else {
          element.textContent = "Немає в наявності";
          element.dataset.state = "out-of-stock";
        }
      })
      .catch(function () {
        element.textContent = "Наявність уточнюється";
        element.dataset.state = "error";
      });
  }

  function hydrateCommerce() {
    document.querySelectorAll("[data-plaik-price]").forEach(hydratePrice);
    document.querySelectorAll("[data-plaik-availability]").forEach(hydrateAvailability);
  }

  async function session() {
    if (csrfToken) return csrfToken;

    var response = await fetch("/api/storefront/session", {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json"},
      body: "{}"
    });

    if (!response.ok) {
      throw new Error("Не вдалося створити сесію магазину.");
    }

    var body = await response.json();
    csrfToken = body.csrf_token;
    return csrfToken;
  }

  async function action(packageId, actionId, payload, key) {
    var token = await session();

    var response = await fetch(
      "/api/storefront/" + packageId + "/actions/" + actionId,
      {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-PLAIK-CSRF-Token": token,
          "Idempotency-Key": key
        },
        body: JSON.stringify(payload)
      }
    );

    if (!response.ok) {
      var message = "Не вдалося виконати запит.";

      try {
        var error = await response.json();
        if (typeof error.detail === "string") {
          message = error.detail;
        }
      } catch (_) {}

      var failure = new Error(message);
      failure.keepIdempotencyKey =
        response.status === 409 || response.status >= 500;

      throw failure;
    }

    return response.json();
  }

  function status(element, message, failed) {
    var output =
      element.querySelector(".plk-action-status") ||
      document.querySelector(".plk-action-status");

    if (!output) return;

    output.textContent = message;
    output.dataset.state = failed ? "error" : "success";
  }

  async function mutate(element, packageId, actionId, payload, success) {
    var key = element.dataset.plaikIdempotencyKey || idempotencyKey();
    element.dataset.plaikIdempotencyKey = key;

    try {
      element.setAttribute("aria-busy", "true");

      await action(packageId, actionId, payload, key);

      delete element.dataset.plaikIdempotencyKey;
      status(element, success, false);

      window.setTimeout(function () {
        window.location.reload();
      }, 250);
    } catch (error) {
      if (
        !error.keepIdempotencyKey &&
        error instanceof TypeError === false
      ) {
        delete element.dataset.plaikIdempotencyKey;
      }

      status(element, error.message, true);
    } finally {
      element.removeAttribute("aria-busy");
    }
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;

    if (form.matches("[data-plaik-cart-add]")) {
      event.preventDefault();

      mutate(
        form,
        "cart",
        "add",
        {
          product_id: form.dataset.productId,
          quantity: Number(new FormData(form).get("quantity"))
        },
        "Товар додано у кошик."
      );
    } else if (form.matches("[data-plaik-cart-set]")) {
      event.preventDefault();

      mutate(
        form,
        "cart",
        "set",
        {
          product_id: form.dataset.productId,
          quantity: Number(new FormData(form).get("quantity"))
        },
        "Кошик оновлено."
      );
    } else if (form.matches("[data-plaik-checkout-place]")) {
      event.preventDefault();

      var data = new FormData(form);
      var payload = {};

      data.forEach(function (value, key) {
        if (typeof value === "string" && value !== "") {
          payload[key] = value;
        }
      });

      mutate(
        form,
        "checkout",
        "place",
        payload,
        "Замовлення оформлено."
      );
    }
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-plaik-cart-remove]");
    if (!button) return;

    mutate(
      button.parentElement,
      "cart",
      "remove",
      {product_id: button.dataset.productId},
      "Товар видалено з кошика."
    );
  });

  async function hydrateCommerceBatch() {
    var priceElements = Array.from(
      document.querySelectorAll("[data-plaik-price]")
    );
    var availabilityElements = Array.from(
      document.querySelectorAll("[data-plaik-availability]")
    );

    if (!priceElements.length && !availabilityElements.length) return;

    try {
      var results = await Promise.all([
        publicQuery("pricing", "prices", {}),
        publicQuery("inventory", "availability-list", {})
      ]);

      var priceRows = Array.isArray(results[0].items)
        ? results[0].items
        : [];
      var stockRows = Array.isArray(results[1].items)
        ? results[1].items
        : [];

      var prices = new Map(
        priceRows.map(function (item) {
          return [String(item.product_id), item];
        })
      );

      var stock = new Map(
        stockRows.map(function (item) {
          return [String(item.product_id), item];
        })
      );

      priceElements.forEach(function (element) {
        var item = prices.get(String(element.dataset.productId || ""));
        if (!item) {
          element.textContent = "Ціна недоступна";
          return;
        }

        element.textContent = formatMoney(
          Number(item.amount_minor),
          String(item.currency)
        );
      });

      availabilityElements.forEach(function (element) {
        var item = stock.get(String(element.dataset.productId || ""));
        var quantity = item ? Number(item.quantity) : 0;

        element.textContent = quantity > 0
          ? "В наявності: " + quantity + " шт."
          : "Немає в наявності";
      });
    } catch (_) {
      priceElements.forEach(function (element) {
        element.textContent = "Ціна тимчасово недоступна";
      });
      availabilityElements.forEach(function (element) {
        element.textContent = "Наявність тимчасово недоступна";
      });
    }
  }

  hydrateCommerceBatch();
})();
