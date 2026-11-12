import { readConfig, startServer } from './server';
import { errorText } from '../shared/errors';

if (import.meta.main) {
  try {
    const running = await startServer(readConfig(process.env, process.argv.includes('--demo')));
    process.stdout.write('cc-runtime-bridge 已启动：http://' + running.server.hostname + ':' + running.server.port + '\n');
    let closing = false;
    const close = async (): Promise<void> => { if (!closing) { closing = true; await running.close(); process.exit(0); } };
    process.on('SIGINT', () => { void close(); });
    process.on('SIGTERM', () => { void close(); });
  } catch (error) {
    process.stderr.write(errorText(error) + '\n');
    process.exitCode = 1;
  }
}
