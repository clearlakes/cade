# uses https://github.com/ShufflePerson/Discord_CDN to get past cdn expiry limits

FROM alpine:3.20

USER root

RUN apk add --update --no-cache git npm && git clone https://github.com/ShufflePerson/Discord_CDN.git cdn

RUN adduser -S cdn
WORKDIR /cdn
RUN chown -R cdn /cdn/
USER cdn

WORKDIR /cdn
COPY .cdn-script.env ./.env
RUN npm run setup
CMD [ "npm", "run", "start" ]