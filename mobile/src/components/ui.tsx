import React from 'react';
import {ActivityIndicator, Pressable, StyleSheet, Text, TextInput, TextInputProps, View} from 'react-native';
import {colors, spacing} from '../theme';

export function ScreenState({loading, error, onRetry}: {loading?: boolean; error?: string; onRetry?: () => void}) {
  return <View style={styles.state}>
    {loading ? <ActivityIndicator size="large" color={colors.primary} /> : <>
      <Text style={styles.stateTitle}>Something needs attention</Text>
      <Text style={styles.muted}>{error}</Text>
      {onRetry && <Button title="Try again" onPress={onRetry} />}
    </>}
  </View>;
}

export function Card({children, style}: React.PropsWithChildren<{style?: object}>) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Button({title, onPress, loading, variant = 'primary', disabled}: {
  title: string; onPress(): void; loading?: boolean; variant?: 'primary' | 'outline' | 'danger'; disabled?: boolean;
}) {
  return <Pressable disabled={disabled || loading} onPress={onPress} style={({pressed}) => [
    styles.button, variant === 'outline' && styles.buttonOutline, variant === 'danger' && styles.buttonDanger,
    (pressed || disabled) && {opacity: 0.7},
  ]}>
    {loading ? <ActivityIndicator color={variant === 'outline' ? colors.primary : '#fff'} /> :
      <Text style={[styles.buttonText, variant === 'outline' && {color: colors.primary}]}>{title}</Text>}
  </Pressable>;
}

export function Field({label, ...props}: TextInputProps & {label: string}) {
  return <View style={{gap: spacing.sm}}><Text style={styles.label}>{label}</Text><TextInput
    placeholderTextColor={colors.muted} {...props} style={[styles.input, props.multiline && {minHeight: 96, textAlignVertical: 'top'}, props.style]}
  /></View>;
}

export function StatusPill({value}: {value: string}) {
  const positive = ['approved', 'completed', 'awarded', 'accepted', 'read'].includes(value.toLowerCase());
  return <View style={[styles.pill, {backgroundColor: positive ? '#d1e7dd' : colors.primarySoft}]}>
    <Text style={{color: positive ? colors.success : colors.primaryDark, fontSize: 12, fontWeight: '700'}}>{value || 'Not set'}</Text>
  </View>;
}

export const sharedStyles = StyleSheet.create({
  screen: {flex: 1, backgroundColor: colors.background},
  content: {padding: spacing.md, gap: spacing.md},
  title: {fontSize: 24, fontWeight: '800', color: colors.primaryDark},
  subtitle: {fontSize: 14, color: colors.muted},
  sectionTitle: {fontSize: 17, fontWeight: '700', color: colors.primaryDark},
  row: {flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm},
});

const styles = StyleSheet.create({
  state: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.md},
  stateTitle: {fontSize: 18, fontWeight: '700', color: colors.primaryDark},
  muted: {color: colors.muted, textAlign: 'center'},
  card: {backgroundColor: colors.surface, borderRadius: 14, padding: spacing.md, borderWidth: 1, borderColor: colors.border, gap: spacing.sm},
  button: {minHeight: 46, backgroundColor: colors.primary, paddingHorizontal: spacing.md, borderRadius: 10, alignItems: 'center', justifyContent: 'center'},
  buttonOutline: {backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.primary},
  buttonDanger: {backgroundColor: colors.danger},
  buttonText: {color: '#fff', fontWeight: '700'},
  label: {fontWeight: '600', color: colors.text},
  input: {minHeight: 48, borderWidth: 1, borderColor: '#d7deea', borderRadius: 10, paddingHorizontal: 14, color: colors.text, backgroundColor: '#fff'},
  pill: {alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999},
});
