import React from 'react';
import {ActivityIndicator, View} from 'react-native';
import {NavigationContainer, DefaultTheme} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import {createBottomTabNavigator} from '@react-navigation/bottom-tabs';
import {Ionicons} from '@expo/vector-icons';
import {StatusBar} from 'expo-status-bar';
import {SafeAreaProvider} from 'react-native-safe-area-context';

import {AuthProvider, useAuth} from './src/auth/AuthContext';
import {colors} from './src/theme';
import {RootStackParamList, TabParamList} from './src/types';
import {LoginScreen} from './src/screens/LoginScreen';
import {DashboardScreen} from './src/screens/DashboardScreen';
import {ProjectsScreen} from './src/screens/ProjectsScreen';
import {ProjectDetailScreen} from './src/screens/ProjectDetailScreen';
import {WorkflowScreen, EnquiryDetailScreen} from './src/screens/WorkflowScreens';
import {AlertsScreen, ProfileScreen} from './src/screens/AccountScreens';
import {ChatScreen} from './src/screens/ChatScreen';
import {SiteUpdateScreen} from './src/screens/SiteUpdateScreen';

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tabs = createBottomTabNavigator<TabParamList>();
const icons: Record<keyof TabParamList, keyof typeof Ionicons.glyphMap> = {Home: 'grid-outline', Projects: 'business-outline', Workflow: 'git-network-outline', Alerts: 'notifications-outline', Profile: 'person-outline'};

function MainTabs() {
  const {user} = useAuth();
  const hasWorkflow = ['Admin', 'Marketing Executive', 'Marketing Manager', 'Estimator', 'Document Controller', 'Project Manager', 'Accountant'].includes(user?.role ?? '');
  return <Tabs.Navigator screenOptions={({route}) => ({headerShown: false, tabBarActiveTintColor: colors.primary, tabBarInactiveTintColor: colors.muted, tabBarStyle: {height: 64, paddingBottom: 8, paddingTop: 6}, tabBarIcon: ({color, size}) => <Ionicons name={icons[route.name]} color={color} size={size} />})}>
    <Tabs.Screen name="Home" component={DashboardScreen} />
    <Tabs.Screen name="Projects" component={ProjectsScreen} />
    {hasWorkflow && <Tabs.Screen name="Workflow" component={WorkflowScreen} />}
    <Tabs.Screen name="Alerts" component={AlertsScreen} />
    <Tabs.Screen name="Profile" component={ProfileScreen} />
  </Tabs.Navigator>;
}

function AppNavigation() {
  const {user, loading} = useAuth();
  if (loading) return <View style={{flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.background}}><ActivityIndicator size="large" color={colors.primary} /></View>;
  if (!user) return <LoginScreen />;
  return <NavigationContainer theme={{...DefaultTheme, colors: {...DefaultTheme.colors, primary: colors.primary, background: colors.background, card: '#fff', text: colors.primaryDark, border: colors.border}}}>
    <Stack.Navigator screenOptions={{headerTintColor: colors.primaryDark, headerBackTitle: 'Back'}}>
      <Stack.Screen name="Main" component={MainTabs} options={{headerShown: false}} />
      <Stack.Screen name="ProjectDetail" component={ProjectDetailScreen} options={({route}) => ({title: route.params.title})} />
      <Stack.Screen name="Chat" component={ChatScreen} options={({route}) => ({title: `${route.params.title} chat`})} />
      <Stack.Screen name="SiteUpdate" component={SiteUpdateScreen} options={{title: 'Site update', presentation: 'modal'}} />
      <Stack.Screen name="EnquiryDetail" component={EnquiryDetailScreen} options={({route}) => ({title: route.params.title})} />
    </Stack.Navigator>
  </NavigationContainer>;
}

export default function App() {
  return <SafeAreaProvider><AuthProvider><StatusBar style="dark" /><AppNavigation /></AuthProvider></SafeAreaProvider>;
}
