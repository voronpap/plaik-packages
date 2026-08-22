# PSP Outbound

Official PLAIK integration 1.0.1. Recorded outbound capture behind the frozen `payments.capture` port. Close-gate traffic uses a fixture host (`https://psp.test/v1/captures`) and never opens a live network socket.

Credentials are `ConnectionRef` pointers only. Package SQL stores `connection_id`, never secret material. Card fields are rejected. Payload `store_id` / `owner_id` are ignored.

Depends only on public `plaik-sdk`.
