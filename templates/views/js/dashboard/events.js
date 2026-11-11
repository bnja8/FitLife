import { bindDashboardClickEvents } from './click.js';
import { bindDashboardFormEvents } from './form-events.js';
import { bindDashboardScanner } from './scanner.js';
import { createDashboardSubmitter } from './submit.js';

export function bindDashboardEvents(context) {
  const submitForm = createDashboardSubmitter(context);
  const scanner = bindDashboardScanner(context);
  bindDashboardClickEvents({ ...context, ...scanner });
  bindDashboardFormEvents({ ...context, submitForm });
}
