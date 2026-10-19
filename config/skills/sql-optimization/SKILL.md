---
name: SQL Optimization
description: Escribir, revisar u optimizar consultas SQL lentas, índices de base de datos y esquemas relacionales.
triggers: SQL consulta query lenta lentísima índice index base de datos JOIN tabla postgres mysql
specialists: [software-engineering]
---
Al trabajar con SQL:

- Antes de optimizar, mide. Pide el `EXPLAIN ANALYZE` si es posible: sin el plan de ejecución estás adivinando.
- Los sospechosos habituales: falta de índice en columnas de `WHERE`/`JOIN`, `SELECT *` cuando solo hacen falta 3 columnas, consultas N+1 desde el código, funciones aplicadas sobre columnas indexadas (`WHERE UPPER(email) = ...` invalida el índice).
- Un índice acelera lecturas y ralentiza escrituras. No propongas índices sin decir qué cuestan.
- Prefiere `EXISTS` sobre `COUNT(*) > 0`, y `JOIN` sobre subconsultas correlacionadas cuando sea equivalente.
- En esquemas: normaliza por defecto, desnormaliza solo con una razón medida.

Muestra siempre la consulta reescrita completa, no solo la descripción del cambio.
