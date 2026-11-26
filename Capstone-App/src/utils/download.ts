import { Platform, Share } from 'react-native';

/**
 * Save a text file. On web the browser downloads it; on iOS/Android the share
 * sheet opens so it can be saved to Files, emailed, or sent to a donation centre.
 */
export async function saveTextFile(filename: string, contents: string, mimeType = 'text/csv'): Promise<void> {
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([contents], { type: `${mimeType};charset=utf-8` }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    return;
  }
  await Share.share({ title: filename, message: contents });
}
