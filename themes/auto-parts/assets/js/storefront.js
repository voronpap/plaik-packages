(function () {
  "use strict";

  var csrfToken = null;

  function idempotencyKey() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
  }

  async function session() {
    if (csrfToken) return csrfToken;
    var response = await fetch("/api/storefront/session", {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json"},
      body: "{}"
    });
    if (!response.ok) throw new Error("Storefront session is unavailable.");
    var body = await response.json();
    csrfToken = body.csrf_token;
    return csrfToken;
  }

  async function action(packageId, actionId, payload) {
    var token = await session();
    var response = await fetch("/api/storefront/" + packageId + "/actions/" + actionId, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-PLAIK-CSRF-Token": token,
        "Idempotency-Key": idempotencyKey()
      },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      var message = "The request could not be completed.";
      try {
        var error = await response.json();
        if (typeof error.detail === "string") message = error.detail;
      } catch (_) {}
      throw new Error(message);
    }
    return response.json();
  }

  function status(element, message, failed) {
    var output = element.querySelector(".plk-action-status") ||
      document.querySelector(".plk-action-status");
    if (!output) return;
    output.textContent = message;
    output.dataset.state = failed ? "error" : "success";
  }

  async function mutate(element, packageId, actionId, payload, success) {
    try {
      element.setAttribute("aria-busy", "true");
      await action(packageId, actionId, payload);
      status(element, success, false);
      window.setTimeout(function () { window.location.reload(); }, 250);
    } catch (error) {
      status(element, error.message, true);
    } finally {
      element.removeAttribute("aria-busy");
    }
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (form.matches("[data-plaik-cart-add]")) {
      event.preventDefault();
      mutate(form, "cart", "add", {
        product_id: form.dataset.productId,
        quantity: Number(new FormData(form).get("quantity"))
      }, "Added to cart.");
    } else if (form.matches("[data-plaik-cart-set]")) {
      event.preventDefault();
      mutate(form, "cart", "set", {
        product_id: form.dataset.productId,
        quantity: Number(new FormData(form).get("quantity"))
      }, "Cart updated.");
    } else if (form.matches("[data-plaik-checkout-place]")) {
      event.preventDefault();
      var data = new FormData(form);
      var payload = {};
      data.forEach(function (value, key) {
        if (typeof value === "string" && value !== "") payload[key] = value;
      });
      mutate(form, "checkout", "place", payload, "Order placed.");
    }
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-plaik-cart-remove]");
    if (!button) return;
    mutate(button.parentElement, "cart", "remove", {
      product_id: button.dataset.productId
    }, "Item removed.");
  });
})();
