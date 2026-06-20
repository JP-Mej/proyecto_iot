# Gestión de usuarios — LSCC

Se agregó un apartado exclusivo para administradores:

```txt
/usuarios
```

## Credenciales iniciales

```txt
Usuario: admin
Contraseña: admin123
Rol: admin
```

## Roles disponibles

- `admin`: puede entrar al dashboard y crear usuarios.
- `usuario`: puede entrar al dashboard, pero no puede acceder a `/usuarios`.

## Sesión única

El sistema mantiene la lógica anterior: si una misma cuenta inicia sesión en otro navegador o dispositivo, la sesión anterior queda inválida automáticamente.

## Uso recomendado

1. Inicia sesión con `admin`.
2. Entra al botón `Usuarios` del dashboard.
3. Crea cuentas con rol `usuario` para operadores o personas que solo deben ver el monitoreo.
4. Crea otro `admin` solo si realmente otra persona debe poder administrar cuentas.
