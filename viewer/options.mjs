import {AdbScrcpyOptions3_3_3} from '@yume-chan/adb-scrcpy';
import {SetClipboardControlMessage} from '@yume-chan/scrcpy/esm/1_21/impl/set-clipboard.js';

export class ViewerOptions extends AdbScrcpyOptions3_3_3 {
  serializeSetClipboardControlMessage(message) {
    // Tango 2.3.0 creates its clipboard serializer only when autosync is enabled.
    // Reuse the exact upstream wire serializer used by 3.3.3, without enabling
    // device-to-host clipboard collection. Sequence zero requires no ACK parser.
    if (message.sequence !== 0n) throw new Error('Explicit clipboard paste uses sequence zero.');
    return SetClipboardControlMessage.serialize(message);
  }
}
