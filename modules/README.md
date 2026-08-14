# Modules

Official PLAIK business-domain packages live here.

Modules own their data and rules. They may expose versioned services/events/hooks through `plaik-sdk`, but must not import private PLAIK Core implementation details or access another package's private storage directly.

Commerce modules such as catalog, inventory, cart, checkout, orders and payments will be added here as independent installable packages.
