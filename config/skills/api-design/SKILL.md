---
name: API Design Review
description: Diseñar o revisar una API REST o RPC: nombres de rutas, códigos de estado, versionado, paginación y contratos de request/response.
triggers: endpoint endpoints REST API ruta contrato versionado paginación
specialists: [software-engineering]
---
Al diseñar o revisar una API:

- Recursos en plural, verbos HTTP con significado (no `/getUser`, sino `GET /users/{id}`).
- Códigos de estado correctos: 400 vs 422 vs 404 vs 409, y por qué.
- Paginación explícita (cursor o offset) en cualquier lista que pueda crecer.
- Versionado desde el día uno (`/v1/`) aunque solo haya una versión.
- Errores en un formato consistente en toda la API, con un código de error legible además del HTTP status.
- Idempotencia en operaciones de escritura donde tenga sentido (claves de idempotencia en POST de pago, por ejemplo).

Propone el contrato completo (rutas, métodos, request/response de ejemplo) antes de entrar en implementación.
