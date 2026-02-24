# Hotel Casa Bella - Sistema de Reservaciones

Sistema web profesional para administrar reservaciones del Hotel Casa Bella con panel de control, validaciones y control de estado.

## Funcionalidades

- Dashboard ejecutivo con métricas clave de ocupación.
- Gestión de habitaciones con capacidad, categoría y tarifa.
- Registro de reservaciones con validaciones de negocio.
- Prevención de sobreventa por traslape de fechas.
- Cambio de estado de reservaciones (confirmed, checked_in, checked_out, cancelled).
- Interfaz HTML/CSS moderna para uso operativo.

## Cómo ejecutar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Abre en navegador: `http://localhost:5000`

## Inicialización de base de datos

La primera ejecución crea automáticamente `hotel_casa_bella.db` con datos semilla de habitaciones.
