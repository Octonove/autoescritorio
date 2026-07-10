# Avisos de terceros (Third-Party Notices)

AutoEscritorio **no empaqueta ni redistribuye componentes de terceros**.

Toda la funcionalidad de la aplicación está construida sobre la biblioteca
estándar de Python (tkinter, ctypes, subprocess, etc.), por lo que el paquete
distribuido no incluye bibliotecas de terceros que requieran avisos de
licencia adicionales.

## Ollama (opcional, no incluido)
Las funciones de IA de AutoEscritorio son opcionales y se comunican con
**Ollama** (https://ollama.com) como servicio externo a través de HTTP.
Ollama **no se empaqueta ni se distribuye** con esta aplicación: el usuario
lo instala por separado si desea usar esas funciones. Ollama se distribuye
bajo licencia MIT; los modelos de lenguaje que el usuario descargue a través
de Ollama tienen sus propias licencias.

El resto del código de AutoEscritorio se distribuye bajo licencia MIT (ver `LICENSE`).
