# Custom Caddy build with rate limiting module.
# The stock caddy:alpine image does not include the rate_limit directive.
# We use xcaddy to compile it in, then copy the binary into the alpine runtime.

FROM caddy:builder AS builder
RUN xcaddy build --with github.com/mholt/caddy-ratelimit

FROM caddy:alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
