# Programa de seguridad, calidad y privacidad de FitLife

**Estado:** línea base inicial; evaluación y documentos de trabajo, no certificación.  
**Fecha de revisión del código:** 9 de noviembre de 2026.

Este documento organiza el trabajo relacionado con ISO/IEC 27034, ISO/IEC/IEEE 12207, ISO/IEC 25010, las leyes chilenas 19.628, 21.459, 21.663 y 21.719, y OWASP SAMM/ASVS. No reemplaza una evaluación independiente, asesoría legal, certificación ISO ni determinación de aplicabilidad regulatoria. Los estados describen únicamente lo que se pudo observar en este repositorio; no acreditan controles de infraestructura, operación o terceros.

## Alcance observado

FitLife es una aplicación Django con base PostgreSQL. El esquema y las vistas manejan RUT, nombres, correo, teléfono, hash de contraseña, roles, membresías, pagos, reservas, actividad/seguimiento de entrenamiento y registros de acceso. El flujo de pago usa Transbank Webpay; el código no debe recibir ni almacenar datos de tarjeta. Hay enlaces de Google Maps y recursos externos de Google Fonts. La organización debe confirmar hosting, correo, backups, procesadores, transferencias y entornos reales.

## Controles técnicos incorporados

- Producción falla al arrancar si falta una clave Django de al menos 50 caracteres aleatorios o si `ALLOWED_HOSTS` está vacío/contiene `*`. `DEBUG` es explícito en `.env.example` para desarrollo y, si no se configura, queda desactivado.
- Cookies de Django seguras en producción, redirección HTTPS y HSTS por defecto cuando `DEBUG=false`; cabeceras anti-sniffing, `DENY` para framing y política de referrer restrictiva.
- El proxy HTTPS solo se considera confiable cuando se configura explícitamente. El proxy debe eliminar encabezados reenviados aportados por clientes.
- Contraseñas nuevas usan los validadores de Django, mínimo 12 caracteres, bloqueo de contraseñas comunes/números y comparación con atributos de cuenta; se limita el máximo a 256 caracteres.
- CI ejecuta pruebas, chequeos de Django, sintaxis JavaScript y `check --deploy` con configuración de producción representativa.
- `.env` permanece excluido de Git; `.env.example` no contiene contraseña de base de datos.
- El esquema ya almacena hashes de contraseñas y hashes SHA-256 de credenciales QR; los tokens QR sin hash se muestran solo al crearse.

Estos controles son una base, no un análisis completo de ASVS ni una declaración de cumplimiento legal.

## Inventario provisional y riesgos de privacidad

| Categoría | Datos observados | Uso aparente | Pendiente |
|---|---|---|---|
| Cuenta/persona | RUT, nombres, apellidos, correo, teléfono | Identidad, inicio de sesión y contacto | Confirmar campos obligatorios, base de licitud y plazos |
| Autenticación | Hash de contraseña, roles, JWT en `sessionStorage` | Acceso y autorización | Migrar el token del navegador a cookie `HttpOnly` con protección CSRF; definir revocación |
| Socio y entrenamiento | Membresías, reservas, asistencia y notas/progreso de seguimiento | Prestación del servicio | Clasificar las notas de entrenamiento y limitar su contenido/retención |
| Accesos | Hash de credencial QR, entradas/salidas, sede y hora | Control de acceso y aforo | Definir plazo de conservación, acceso administrativo y auditoría |
| Pagos | Orden, estado y metadatos de transacción | Conciliar compras | Verificar configuración, datos recibidos y retención con Transbank; no registrar PAN/CVV |
| Personal | Identidad, RUT, correo, rol y perfil profesional | Operación del gimnasio | Definir responsables y plazos para cuentas inactivas |

El inventario se infirió del código y del esquema SQL, no de entrevistas ni del entorno productivo. Confirmar si existen datos, integraciones o tratamientos adicionales.

## Matriz de trabajo

| Marco | Estado en este repositorio | Próximo control verificable |
|---|---|---|
| ISO/IEC 27034 | Parcial: hay endurecimiento de configuración y validaciones; no existe un modelo aprobado de seguridad de aplicaciones ni evaluación de riesgos por versión | Definir modelo de seguridad de la organización, activos, amenazas, controles y evidencia de aceptación |
| ISO/IEC/IEEE 12207 | Parcial: CI nuevo ejecuta pruebas y comprobaciones básicas; no se verificaron aprobaciones de cambios, releases, mantenimiento ni adquisición | Aprobar ciclo de vida, roles, revisión independiente, control de cambios, releases, proveedores y gestión de fin de vida |
| ISO/IEC 25010 | Parcial: pruebas automatizadas y comprobaciones sintácticas; sin objetivos de calidad, cobertura/umbral ni evaluación de producción | Establecer métricas y criterios de aceptación para seguridad, fiabilidad, rendimiento, mantenibilidad, compatibilidad y usabilidad |
| Ley 19.628 | No evaluada legalmente. El código trata datos personales identificables | Confirmar responsable, finalidades, fundamento, información a titulares, contratos, derechos, retención y medidas aplicables |
| Ley 21.719 | Preparación prioritaria. Publicada en 2024 y con entrada en vigor prevista para el 1 de diciembre de 2026; validar texto vigente, transitorios y obligaciones aplicables al tratamiento concreto | Asesoría legal para gobernanza, transparencia, bases de licitud, ejercicio de derechos, encargados, incidentes y evaluación de impacto cuando corresponda |
| Ley 21.459 | No existe evaluación jurídica/técnica formal ni procedimiento documentado de preservación de evidencia y respuesta | Establecer controles de acceso, monitoreo, preservación de evidencia, escalamiento y respuesta a incidentes |
| Ley 21.663 | Aplicabilidad organizacional no determinada; no se afirma que FitLife sea entidad regulada, servicio esencial u operador de importancia vital | Determinar con asesoría competente si la organización cae en el ámbito de la ley y qué obligaciones de reporte/gobierno le aplican |
| OWASP ASVS | Sin verificación requisito por requisito. ASVS 5.0.0 es una referencia técnica de trabajo; nivel objetivo aún no aprobado | Acordar nivel y perfil de requisitos; vincular cada requisito a prueba, evidencia, responsable y excepción aprobada |
| OWASP SAMM | No se ha ejecutado una evaluación de madurez | Hacer evaluación inicial por prácticas SAMM, acordar objetivo y repetirla periódicamente |

La aplicabilidad y las obligaciones legales pueden depender de la entidad, el tratamiento, el contrato, la infraestructura y los hechos. Los estados “pendiente” no deben cambiarse a “cumple” sin evidencia revisada.

## Brechas prioritarias antes de producción

1. **Gobernanza de privacidad:** la aplicación no tiene aviso de privacidad aprobado ni constan responsable legal, contacto, finalidades completas, bases jurídicas, periodos de conservación, destinatarios, encargados, transferencias o procedimiento de derechos. No publicar un aviso con datos ficticios.
2. **Credenciales del navegador:** el JWT se guarda en `sessionStorage`; un XSS podría leerlo. Diseñar y probar una migración a cookie `HttpOnly`, `Secure`, `SameSite` y protección CSRF antes de cambiar el modo de autenticación.
3. **Fuerza bruta:** no se verificó limitación de intentos de login/registro ni una protección distribuida entre instancias. Implementar rate limiting con almacenamiento compartido y monitoreo antes de exponer el login.
4. **Auditoría:** no se verificó un registro de auditoría inmutable de acciones administrativas, accesos a datos, cambios de roles ni gestión de sesiones.
5. **Derechos y retención:** no se verificó flujo de acceso/exportación, rectificación, supresión/bloqueo, oposición u otros derechos aplicables; tampoco calendario de retención, borrado verificable o retenciones legales.
6. **Incidentes y continuidad:** no se verificaron responsables, contactos, clasificación, tiempos de escalamiento/notificación, preservación de evidencia, backups cifrados ni pruebas de restauración.
7. **Cadena de suministro:** CI aún instala rangos de dependencias sin lockfile, análisis de vulnerabilidades, SBOM, procedencia ni revisión de acciones externas. Evaluar y fijar versiones/acciones con un proceso de actualización.
8. **Seguridad de contenido y XSS:** no se verificó CSP; la interfaz carga recursos externos y debe diseñarse una política compatible con sus scripts/estilos antes de imponerla.
9. **Pruebas independientes:** no se ejecutó una auditoría de código, prueba de penetración, revisión de configuración de infraestructura ni evaluación ASVS.

## Decisiones requeridas de la organización

Antes de activar datos reales, asignar responsables y aprobar por escrito:

- identidad legal del responsable y contacto de privacidad/seguridad;
- finalidades y fundamento jurídico por dato y proceso, diferenciando prestación del servicio, pagos, seguridad y comunicaciones;
- datos estrictamente necesarios, campos opcionales, destinatarios, encargados, ubicación y transferencias;
- periodos por categoría, reglas de borrado y excepciones de conservación;
- canal, verificación de identidad, responsables y plazos para solicitudes de titulares;
- quién recibe y evalúa incidentes, criterios de escalamiento y obligaciones de notificación según aplicabilidad;
- aplicabilidad de Ley 21.663 y designación de alcance; objetivo SAMM y nivel/perfil ASVS;
- infraestructura, cifrado, backups, restauración, RTO/RPO, monitoreo, acceso privilegiado y rotación de secretos;
- cambios de terceros, pagos, medios externos y contratos de tratamiento.

La entrada en vigor indicada para la Ley 21.719 requiere confirmación contra la publicación oficial y revisión de sus disposiciones transitorias y modificaciones posteriores antes de tomar decisiones de cumplimiento.

## Revisión normativa

Mantener una copia de trabajo de las versiones vigentes y transitorios oficiales de las normas; registrar fecha, asesor legal revisor, interpretaciones y decisiones. Fuentes de consulta: [Biblioteca del Congreso Nacional - Ley Chile](https://www.bcn.cl/leychile/), [OWASP ASVS](https://asvs.owasp.org/), [OWASP SAMM](https://owaspsamm.org/). Verificar en fuentes oficiales el texto vigente, su entrada en vigor y la aplicación a FitLife; los estándares ISO deben consultarse en la edición adquirida/aplicable.

## Evidencia y ciclo de revisión

CI es evidencia de ejecución de pruebas de este código en el commit correspondiente; no representa pruebas de producción. Para cada release, conservar commit, resultado de pruebas, revisión/aprobación, dependencias, migraciones SQL, cambios de configuración, riesgos aceptados y plan de reversa. Revisar esta matriz al menos en cada release relevante y cuando cambien leyes, proveedores, arquitectura o datos tratados.

Como proceso propuesto para aprobación organizacional, cada cambio debe:

1. registrar requerimiento, responsable, criterios de aceptación y si cambia datos personales, roles, pagos, integraciones o superficie de red;
2. analizar amenazas/impacto de privacidad para cambios de alto riesgo y decidir controles antes de programar;
3. recibir revisión por otra persona, validar autorización, manejo de errores, datos de entrada/salida, dependencias y migraciones;
4. pasar CI y pruebas específicas del cambio; la revisión de seguridad no puede reemplazarse por el resultado de CI;
5. aprobar despliegue, backup/restauración cuando corresponda, configuración segura, compatibilidad de esquema y reversa;
6. revisar eventos/alertas y vulnerabilidades de dependencias en operación; documentar respuesta, corrección y aprendizaje;
7. al retirar un servicio, revocar secretos/accesos, definir borrado o conservación legal y conservar evidencia necesaria.

Este proceso aún no está aprobado ni aplicado por reglas de ramas, responsables o evidencia de releases; esos elementos se deben configurar en el repositorio y la organización.
