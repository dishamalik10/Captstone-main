import { Image, type ImageProps } from 'expo-image';
import { cn } from '@/utils/helpers';

interface AppImageProps extends ImageProps {
  className?: string;
}

/** expo-image over a warm surface colour, which is the placeholder while loading and the fallback if a load fails. */
export function AppImage({ className, ...props }: AppImageProps) {
  return (
    <Image
      transition={280}
      {...props}
      className={cn('bg-surface-raised', className)}
    />
  );
}
