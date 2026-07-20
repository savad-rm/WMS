import React, {useState} from 'react';
import {Image, KeyboardAvoidingView, Platform, SafeAreaView, StyleSheet, Text, View} from 'react-native';
import {useAuth} from '../auth/AuthContext';
import {Button, Field} from '../components/ui';
import {colors, spacing} from '../theme';

export function LoginScreen() {
  const {signIn} = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const submit = async () => {
    setLoading(true); setError('');
    try { await signIn(email.trim(), password); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Sign in failed.'); }
    finally { setLoading(false); }
  };
  return <SafeAreaView style={styles.screen}><KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.center}>
    <View style={styles.brand}><View style={styles.logo}><Text style={styles.logoText}>W</Text></View><Text style={styles.title}>WMS Mobile</Text><Text style={styles.subtitle}>Projects, people and site operations in one place.</Text></View>
    <View style={styles.form}>
      <Field label="Work email" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" autoComplete="email" />
      <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry autoComplete="current-password" />
      {!!error && <Text style={styles.error}>{error}</Text>}
      <Button title="Sign in" onPress={submit} loading={loading} disabled={!email || !password} />
      <Text style={styles.help}>Use the same account as the WMS web application.</Text>
    </View>
  </KeyboardAvoidingView></SafeAreaView>;
}

const styles = StyleSheet.create({
  screen: {flex: 1, backgroundColor: colors.background}, center: {flex: 1, justifyContent: 'center', padding: spacing.lg, gap: spacing.xl},
  brand: {alignItems: 'center', gap: spacing.sm}, logo: {width: 72, height: 72, borderRadius: 20, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center'},
  logoText: {fontSize: 36, color: '#fff', fontWeight: '900'}, title: {fontSize: 30, color: colors.primaryDark, fontWeight: '900'},
  subtitle: {color: colors.muted, textAlign: 'center', maxWidth: 300}, form: {backgroundColor: '#fff', borderRadius: 18, padding: spacing.lg, gap: spacing.md, borderWidth: 1, borderColor: colors.border},
  error: {color: colors.danger}, help: {color: colors.muted, textAlign: 'center', fontSize: 12},
});
