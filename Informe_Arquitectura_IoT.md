

**UNIVERSIDAD NACIONAL MAYOR DE SAN MARCOS**

Facultad de Ingeniería de Sistemas e Informática

**INFORME: ARQUITECTURA EN CAPAS DEL MODELO DE REFERENCIA IoT**

*Basado en: Sesión 01, Sesión 02 e Internet de las Cosas — Recomendación UIT-T Y.2060 (06/2012)*

Curso: Internet de las Cosas  
Ing. Armando Fermín Pérez

Lima, Perú — 2025

# **1\. Introducción**

El presente informe detalla la arquitectura en capas del modelo de referencia de Internet de las Cosas (IoT), conforme a la Recomendación UIT-T Y.2060 publicada en junio de 2012 por la Unión Internacional de Telecomunicaciones, y al contenido desarrollado en las Sesiones 01 y 02 del curso.

El modelo de referencia IoT consta de cuatro capas funcionales y dos conjuntos de capacidades transversales que atraviesan la totalidad del modelo: las capacidades de gestión y las capacidades de seguridad. Cada capa cumple una función específica dentro del ecosistema IoT y juntas permiten la interconexión de objetos físicos y virtuales para la prestación de servicios avanzados.

| Definición IoT | Infraestructura mundial para la sociedad de la información que propicia la prestación de servicios avanzados mediante la interconexión de objetos (físicos y virtuales) gracias a la interoperatividad de tecnologías de la información y la comunicación presentes y futuras. (UIT-T Y.2060, §3.2.2) |
| :---: | :---- |

# **2\. Estructura General del Modelo de Referencia IoT**

El modelo de referencia IoT, definido en el §8 del estándar UIT-T Y.2060, está compuesto por cuatro capas y dos capacidades transversales:

* Capa de aplicación

* Capa de apoyo a servicios y aplicaciones (middleware)

* Capa de red

* Capa de dispositivo

De forma transversal a las cuatro capas:

* Capacidades de gestión (genéricas y específicas)

* Capacidades de seguridad (genéricas y específicas)

# **3\. Capa de Dispositivo**

La capa de dispositivo es la capa base del modelo de referencia IoT. Es la que interactúa directamente con el mundo físico a través de sensores, actuadores y pasarelas. Según el §8.4 del UIT-T Y.2060, las capacidades de esta capa se clasifican lógicamente en dos tipos: capacidades de dispositivo y capacidades de pasarela.

## **3.1. Capacidades de Dispositivo**

Las capacidades de dispositivo incluyen las siguientes funciones definidas en el §8.4 del Y.2060:

* **Interacción directa con la red de comunicaciones:** Los dispositivos pueden recabar y cargar información directamente (sin recurrir a capacidades de pasarela) en la red de comunicación, y pueden recibir directamente información, por ejemplo instrucciones, de la red de comunicación.

* **Interacción indirecta con la red de comunicación:** Los dispositivos pueden recabar y cargar información indirectamente en la red de comunicación, es decir, mediante capacidades de pasarela. Además, los dispositivos pueden recibir información indirectamente de la red.

* **Redes ad-hoc:** Los dispositivos pueden construir redes de manera ad-hoc en algunas circunstancias cuando sea necesario para aumentar la capacidad evolutiva y la velocidad de despliegue.

* **Modo reposo y activo:** Las capacidades de dispositivo deben disponer de mecanismos para pasar a los modos reposo y activo a fin de ahorrar energía.

Nota importante del Y.2060 §8.4: No es obligatorio que un mismo dispositivo pueda efectuar la interacción directa e indirecta con la red de comunicación.

### **3.1.1. Tipos de Dispositivos IoT (Y.2060 §6.2)**

El estándar clasifica los dispositivos IoT en cuatro categorías:

| Tipo de dispositivo | Definición según Y.2060 §6.2 |
| :---- | :---- |
| **Dispositivo de transporte de datos** | Dispositivo anexo a un objeto físico para conectar indirectamente el objeto físico con las redes de comunicación. |
| **Dispositivo de adquisición de datos** | Dispositivo de lectura/escritura con capacidad para interactuar con objetos físicos. La interacción puede suceder indirectamente a través de dispositivos de transporte de datos, o directamente. Las tecnologías utilizadas para la interacción son del tipo de radiofrecuencia, infrarrojo, óptico o galvánico. |
| **Dispositivo de detección y accionamiento** | Detecta o mide información de su entorno y la convierte en señales electrónicas digitales. También puede convertir señales electrónicas digitales en operaciones. Por lo general, forman redes locales que se comunican entre sí utilizando tecnologías alámbricas o inalámbricas y utilizan pasarelas para conectarse con las redes de comunicación. |
| **Dispositivo genérico** | Dispositivo con capacidades de procesamiento y comunicación que puede comunicarse con las redes de comunicación mediante tecnologías alámbricas e inalámbricas. Incluye máquinas industriales, electrodomésticos y teléfonos inteligentes. |

## **3.2. Capacidades de Pasarela**

Las capacidades de pasarela son el segundo tipo de capacidades de la capa de dispositivo. Según el Y.2060 §8.4, incluyen:

* **Soporte de interfaces múltiples:** En la capa de dispositivo, las capacidades de pasarela soportan dispositivos conectados mediante diferentes tipos de tecnologías alámbricas e inalámbricas, tales como CAN, ZigBee, Bluetooth o Wi-Fi. En la capa de red, las capacidades de pasarela pueden comunicarse a través de diversas tecnologías, tales como PSTN, redes 2G o 3G, LTE, Ethernet o DSL.

* **Conversión de protocolo:** Existen dos situaciones donde se necesitan capacidades de pasarela: cuando las comunicaciones en la capa de dispositivo utilizan protocolos diferentes (ej. ZigBee y Bluetooth), o cuando en la comunicación intervienen la capa de dispositivo y la de red con protocolos distintos en cada una (ej. ZigBee en la capa de dispositivo y 3G en la capa de red).

# **4\. Capa de Red**

La capa de red se encuentra entre la capa de dispositivo y la capa de apoyo a servicios y aplicaciones. Su función principal es transferir datos adquiridos por los dispositivos a las aplicaciones y otros dispositivos, así como instrucciones de las aplicaciones a los dispositivos. Según el Y.2060 §8.3, consiste en dos tipos de capacidades:

## **4.1. Capacidades de Red**

Ofrecen funciones de control de la conectividad en red, tales como:

* Funciones de control de acceso

* Control y recursos de transporte

* Gestión de la movilidad

* Autentificación, autorización y contabilidad (AAA)

## **4.2. Capacidades de Transporte**

Centradas en suministrar conectividad para el transporte de:

* Información y datos específicos de servicios y aplicaciones IoT

* Información de control y gestión relacionada con IoT

Según el Y.2060 §6.2, la infraestructura de red IoT puede crearse mediante redes existentes, como las redes convencionales basadas en TCP/IP, y/o redes evolutivas, tales como las redes de la próxima generación (NGN).

## **4.3. Protocolos por Capa (Sesión 02 — Al-Fuqaha et al. 2015\)**

La Sesión 02 presenta los protocolos IoT más prominentes clasificados por tipo:

| Tipo de protocolo | Protocolos |
| :---- | :---- |
| **Application** | DDS, CoAP, AMQP, MQTT, MQTT-SN, XMPP, HTTP REST |
| **Service discovery** | mDNS, DNS-SD |
| **Middleware layer network protocol** | IPv4/IPv6 |
| **Sensing layer network protocol** | 2G/3G/LTE, 6LoWPAN, BLE, DASH7, IEEE 802.15.4, LoRa, RFID, Sigfox, Wize, Z-Wave, Zigbee |

# **5\. Capa de Apoyo a Servicios y Aplicaciones (Middleware)**

La capa de apoyo a servicios y aplicaciones se ubica entre la capa de red y la capa de aplicación. Según el Y.2060 §8.2, consiste en dos grupos de capacidades:

## **5.1. Capacidades de Soporte Genéricas**

Son capacidades comunes que pueden utilizarlas diferentes aplicaciones IoT. Ejemplos definidos en el Y.2060:

* Procesamiento de datos

* Almacenamiento de datos

Estas capacidades también pueden utilizarlas otras capacidades específicas para, por ejemplo, crear otras capacidades específicas.

## **5.2. Capacidades de Soporte Específicas**

Son capacidades para atender las necesidades particulares de diversas aplicaciones. En realidad, pueden consistir en diversos grupos de capacidades precisas que ofrecen distintas funciones de apoyo a las diferentes aplicaciones IoT.

## **5.3. Términos Clave de Arquitectura (Sesión 02\)**

La Sesión 02 define los siguientes conceptos relacionados con esta capa:

| Plataforma | Entorno (hardware y software) donde se alojan y ejecutan las aplicaciones de software. La Plataforma IoT aloja el middleware de IoT. |
| :---: | :---- |

| Middleware | Aplicaciones de software que proporcionan servicios a otras aplicaciones de software. |
| :---: | :---- |

| Framework IoT | Entornos de software que proporcionan software específico de aplicación con una funcionalidad específica. Proporciona el entorno que permite la comunicación entre el middleware de IoT y otros elementos de IoT, como aplicaciones, sensores y actuadores. |
| :---: | :---- |

## **5.4. Arquitecturas de Frameworks IoT (Sesión 02\)**

La Sesión 02 presenta distintos modelos de arquitectura para frameworks IoT, basados en Al-Fuqaha et al. (2015) y Peralta et al. (2022):

| Modelo | Capas principales |
| :---- | :---- |
| **Modelo 3 capas** | Perception Layer → Network Layer → Application Layer |
| **Basado en Middleware** | Application → Middleware → Coordination → Backbone Network → Access / Edge |
| **Basado en SOA** | Applications → Service Composition → Service Management → Object Abstraction → Objects |
| **Modelo 5 capas** | Business Layer → Application Layer → Service Management → Object Abstraction → Objects |
| **Modelo ITU-T Y.2060** | Capa Aplicación → Apoyo a servicios → Red → Dispositivo \+ Gestión y Seguridad transversales |

# **6\. Capa de Aplicación**

La capa de aplicación es la capa más alta del modelo de referencia IoT. Según el Y.2060 §8.1, esta capa contiene las aplicaciones IoT.

Las aplicaciones IoT son de diversos tipos, por ejemplo: sistemas de transporte inteligente, red de suministro eléctrico, cibersalud u hogar inteligente. Pueden basarse en plataformas de aplicación patentadas, pero también en plataformas de servicios/aplicaciones comunes que ofrecen capacidades genéricas tales como autentificación, gestión de dispositivos, tasación y contabilidad.

## **6.1. Dominios de Aplicación IoT en Smart City (Sesión 02\)**

La Sesión 02 presenta la categorización de frameworks IoT en el dominio Smart City, distinguiendo entre dominios hard (infraestructura física) y soft (servicios sociales):

* Smart infrastructure (dominio hard) — mayor representación

* Smart environment (dominio hard)

* Smart living (dominio hard)

* Smart mobility (dominio hard)

* Smart economy (dominio soft)

* Smart citizens (dominio soft)

* Smart governance (dominio soft)

## **6.2. Interfaces y Entrega de Datos (Sesión 02\)**

Según el estudio de Peralta et al. (2022) presentado en la Sesión 02:

| Interfaces habilitadas (capa aplicación) Mobile application interface (23 frameworks) Web interface (22 frameworks) PC application interface (4 frameworks) | Entrega de datos (capa aplicación) Real time — tiempo real (28 frameworks) On demand — bajo demanda (15 frameworks) |
| :---- | :---- |

# **7\. Capacidades de Gestión (Transversal)**

Las capacidades de gestión son transversales: cruzan las cuatro capas del modelo de referencia IoT. Según el Y.2060 §8.5, abarcan las clases tradicionales FCAPS aplicadas al contexto IoT.

| FCAPS | Fallos (Fault), Configuración (Configuration), Contabilidad (Accounting), Rendimiento (Performance) y Seguridad (Security). Son las clases de gestión tradicionales de redes de comunicaciones, también aplicables en IoT. |
| :---: | :---- |

## **7.1. Capacidades de Gestión Genéricas**

Las capacidades de gestión genéricas en IoT son esencialmente las siguientes, según el Y.2060 §8.5:

### **Gestión de dispositivos**

Incluye las siguientes funciones:

* Activación y desactivación de dispositivos remotos

* Diagnóstico

* Actualización del firmware y/o del software

* Gestión del estado de trabajo del dispositivo

### **Gestión de la topología de red local**

Administración de la topología de la red local de dispositivos IoT.

### **Gestión del tráfico y la congestión**

Incluye:

* Detección de las condiciones de saturación de red

* Aplicación de reserva de recursos para los flujos de datos esenciales para la vida o urgentes

## **7.2. Capacidades de Gestión Específicas**

Las capacidades de gestión específicas están estrechamente relacionadas con los requisitos específicos de la aplicación. Por ejemplo: requisitos de control de la línea de transmisión por la red de suministro eléctrico inteligente.

# **8\. Capacidades de Seguridad (Transversal)**

Las capacidades de seguridad son también transversales al modelo de referencia IoT. Según el Y.2060 §8.6, se dividen en dos tipos: genéricas y específicas.

## **8.1. Capacidades de Seguridad Genéricas**

Son independientes de la aplicación. El Y.2060 §8.6 las detalla por capa:

| Capa | Capacidades de seguridad genéricas según Y.2060 §8.6 |
| :---- | :---- |
| **Capa de aplicación** | Autorización, autentificación, confidencialidad de datos de aplicación y protección de la integridad, protección de la privacidad, auditorías de seguridad y antivirus. |
| **Capa de red** | Autorización, autentificación, confidencialidad de datos de señalización y de datos de uso, y protección de la integridad de señalización. |
| **Capa de dispositivo** | Autentificación, autorización, validación de la integridad del dispositivo, control de acceso, confidencialidad de datos y protección de la integridad. |

## **8.2. Capacidades de Seguridad Específicas**

Las capacidades de seguridad específicas están estrechamente relacionadas con los requisitos específicos de la aplicación. Un ejemplo indicado en el Y.2060 §8.6 son los requisitos de seguridad para el pago con el móvil.

# **9\. Requisitos de Alto Nivel de IoT (Y.2060 §7.2)**

El Y.2060 §7.2 establece los siguientes requisitos de alto nivel para IoT, que complementan la arquitectura en capas:

| Conectividad basada en la identificación | La IoT necesita que se establezca conectividad entre un objeto y IoT con arreglo al identificador del objeto. Para ello puede ser necesario además procesar de manera unificada identificadores posiblemente heterogéneos. |
| :---: | :---- |

| Compatibilidad | Es indispensable garantizar la compatibilidad entre sistemas heterogéneos y distribuidos para el suministro y consumo de diversos tipos de información y servicios. |
| :---: | :---- |

| Redes automáticas | Es necesario que las funciones de control de red de IoT soporten las redes automáticas (autogestión, autoconfiguración, autorestablecimiento, autooptimización y autoprotección), a fin de adaptarse a los diferentes dominios de aplicación. |
| :---: | :---- |

| Configuración automática de servicios | Es preciso poder configurar los servicios a partir de los datos de los objetos adquiridos, comunicados y procesados automáticamente con arreglo a las reglas configuradas por los operadores o personalizadas por los clientes. |
| :---: | :---- |

| Capacidades basadas en la ubicación | IoT debe dar soporte a capacidades basadas en la ubicación. Las comunicaciones y servicios relacionados con objetos dependerán de la información sobre la ubicación de los objetos y/o los usuarios. |
| :---: | :---- |

| Seguridad | En IoT, todo objeto está conectado, lo que conlleva considerables amenazas de seguridad en ámbitos tales como la confidencialidad, autenticidad e integridad de datos y servicios. |
| :---: | :---- |

| Protección de la privacidad | IoT tiene que dar soporte a la protección de la privacidad durante la transmisión, combinación, almacenamiento, minería y procesamiento de datos. La protección de la privacidad no debe ser un obstáculo a la autentificación de las fuentes de datos. |
| :---: | :---- |

| Servicios relacionados con el cuerpo humano | IoT debe dar soporte a estos servicios con calidad y seguridad elevadas. Cada país aplica leyes y reglamentos diferentes a estos servicios. |
| :---: | :---- |

| Autoconfiguración (plug and play) | IoT debe soportar la autoconfiguración que permite generar, componer o adquirir configuraciones semánticas para la integración paulatina y la cooperación de los objetos interconectados con aplicaciones. |
| :---: | :---- |

| Capacidad de administración | IoT debe dar soporte a la capacidad de administración para garantizar el funcionamiento normal de la red. El proceso global de funcionamiento debe poderlo gestionar las partes pertinentes. |
| :---: | :---- |

# **10\. Conclusiones**

El modelo de referencia IoT definido en el UIT-T Y.2060 presenta una arquitectura en capas clara y funcional que permite organizar la complejidad de los sistemas IoT:

* **Capa de dispositivo:** Es la base del modelo. Interactúa con el mundo físico mediante cuatro tipos de dispositivos y gestiona la comunicación directa, indirecta y la conversión de protocolos a través de pasarelas.

* **Capa de red:** Transporta los datos entre dispositivos y aplicaciones. Provee capacidades de conectividad y transporte sobre infraestructuras existentes o de próxima generación.

* **Capa de apoyo a servicios y aplicaciones:** Actúa como middleware. Ofrece capacidades genéricas reutilizables y capacidades específicas por aplicación, alojadas en la plataforma IoT.

* **Capa de aplicación:** Contiene las aplicaciones IoT finales, que pueden ser de dominio hard o soft según el ámbito de la Smart City u otro dominio.

* **Capacidades de gestión (transversal):** Cubren FCAPS para toda la arquitectura, incluyendo gestión de dispositivos, topología y tráfico.

* **Capacidades de seguridad (transversal):** Garantizan autenticación, autorización, confidencialidad e integridad en cada capa, tanto de forma genérica como específica por aplicación.

# **Referencias**

Unión Internacional de Telecomunicaciones. (2012). Recomendación UIT-T Y.2060 (06/2012): Descripción general de Internet de los objetos. UIT-T.

Fermín Pérez, A. (2025). Sesión 01: Introducción a Internet de las Cosas \[Diapositivas\]. Universidad Nacional Mayor de San Marcos, Facultad de Ingeniería de Sistemas e Informática.

Fermín Pérez, A. (2025). Sesión 02: Arquitectura de Internet de las Cosas \[Diapositivas\]. Universidad Nacional Mayor de San Marcos, Facultad de Ingeniería de Sistemas e Informática.