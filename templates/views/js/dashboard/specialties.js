export const instructorSpecialties = {
  MONITOR: {
    label: 'Monitor',
    heading: 'Gestión de clases y asistencia',
    description: 'Programa tus clases grupales, consulta participantes y registra su asistencia.',
    navigation: [
      ['home', 'Mi jornada', '⌂'],
      ['sessions', 'Mis clases', '◷'],
      ['attendance', 'Asistencia y participantes', '✓'],
      ['credential', 'Mi credencial QR', '⌁'],
    ],
    cards: [
      { route: 'sessions', title: 'Mis clases', description: 'Programa tu agenda y consulta el historial', icon: '◷' },
      { route: 'attendance', title: 'Participantes y asistencia', description: 'Consulta inscritos y registra asistencia', icon: '✓' },
      { route: 'credential', title: 'Mi credencial QR', description: 'Accede a tu sede como parte del equipo', icon: '⌁' },
    ],
    recordsTitle: null,
  },
  PERSONAL_TRAINER: {
    label: 'Entrenador personal',
    heading: 'Entrenamiento personal',
    description: 'Registra planes, objetivos y observaciones del entrenamiento de tus socios.',
    navigation: [
      ['home', 'Mi jornada', '⌂'],
      ['team', 'Planes y progreso', '↗'],
      ['credential', 'Mi credencial QR', '⌁'],
    ],
    cards: [
      { route: 'team', title: 'Planes y progreso', description: 'Registra objetivos, rutinas y avances', icon: '↗' },
      { route: 'credential', title: 'Mi credencial QR', description: 'Accede a tu sede como parte del equipo', icon: '⌁' },
    ],
    recordsTitle: 'Historial de entrenamiento personal',
  },
  COACH: {
    label: 'Coach',
    heading: 'Acompañamiento y constancia',
    description: 'Acompaña los objetivos de tus socios y registra sus avances y adherencia.',
    navigation: [
      ['home', 'Mi jornada', '⌂'],
      ['team', 'Objetivos y adherencia', '↗'],
      ['credential', 'Mi credencial QR', '⌁'],
    ],
    cards: [
      { route: 'team', title: 'Objetivos y adherencia', description: 'Registra metas, compromisos y avances', icon: '↗' },
      { route: 'credential', title: 'Mi credencial QR', description: 'Accede a tu sede como parte del equipo', icon: '⌁' },
    ],
    recordsTitle: 'Historial de objetivos y sesiones',
  },
  PREPARADOR_FISICO: {
    label: 'Preparador físico',
    heading: 'Evaluación y rendimiento físico',
    description: 'Registra evaluaciones, planificación de acondicionamiento y evolución del rendimiento.',
    navigation: [
      ['home', 'Mi jornada', '⌂'],
      ['team', 'Evaluaciones y rendimiento', '↗'],
      ['credential', 'Mi credencial QR', '⌁'],
    ],
    cards: [
      { route: 'team', title: 'Evaluaciones y rendimiento', description: 'Registra pruebas, cargas y evolución', icon: '↗' },
      { route: 'credential', title: 'Mi credencial QR', description: 'Accede a tu sede como parte del equipo', icon: '⌁' },
    ],
    recordsTitle: 'Historial de evaluaciones y rendimiento',
  },
};

export function getInstructorSpecialty(data) {
  return instructorSpecialties[data?.professional_profile?.tipo] || null;
}
