REGION_CITIES = {
    'Arica y Parinacota': ('Arica', 'Putre', 'Camarones', 'General Lagos'),
    'Tarapacá': ('Iquique', 'Alto Hospicio', 'Pozo Almonte', 'Pica', 'Huara'),
    'Antofagasta': (
        'Antofagasta', 'Calama', 'Mejillones', 'Tocopilla', 'San Pedro de Atacama', 'Taltal',
    ),
    'Atacama': ('Copiapó', 'Vallenar', 'Caldera', 'Chañaral', 'Diego de Almagro', 'Huasco'),
    'Coquimbo': (
        'La Serena', 'Coquimbo', 'Ovalle', 'Illapel', 'Vicuña', 'Los Vilos', 'Andacollo',
    ),
    'Valparaíso': (
        'Valparaíso', 'Viña del Mar', 'Quilpué', 'Villa Alemana', 'San Antonio', 'Quillota',
        'Los Andes', 'San Felipe', 'Concón', 'La Calera',
    ),
    'Metropolitana de Santiago': (
        'Santiago', 'Puente Alto', 'Maipú', 'Las Condes', 'La Florida', 'San Bernardo',
        'Peñalolén', 'Pudahuel', 'Quilicura', 'Vitacura', 'Ñuñoa', 'Melipilla', 'Talagante',
    ),
    "Libertador General Bernardo O'Higgins": (
        'Rancagua', 'Machalí', 'San Fernando', 'Rengo', 'Santa Cruz', 'Pichilemu',
    ),
    'Maule': ('Talca', 'Curicó', 'Linares', 'Constitución', 'Cauquenes', 'Parral'),
    'Ñuble': ('Chillán', 'San Carlos', 'Bulnes', 'Yungay', 'Quirihue'),
    'Biobío': (
        'Concepción', 'Talcahuano', 'Los Ángeles', 'Coronel', 'San Pedro de la Paz', 'Chiguayante',
        'Lota', 'Tomé',
    ),
    'La Araucanía': ('Temuco', 'Padre Las Casas', 'Villarrica', 'Pucón', 'Angol', 'Victoria'),
    'Los Ríos': ('Valdivia', 'La Unión', 'Río Bueno', 'Panguipulli'),
    'Los Lagos': ('Puerto Montt', 'Osorno', 'Puerto Varas', 'Castro', 'Ancud', 'Quellón'),
    'Aysén del General Carlos Ibáñez del Campo': (
        'Coyhaique', 'Puerto Aysén', 'Chile Chico', 'Cochrane',
    ),
    'Magallanes y de la Antártica Chilena': (
        'Punta Arenas', 'Puerto Natales', 'Porvenir', 'Puerto Williams',
    ),
}


def valid_region_city(region, city):
    return (
        isinstance(region, str)
        and region in REGION_CITIES
        and isinstance(city, str)
        and bool(city.strip())
        and len(city.strip()) <= 100
    )
